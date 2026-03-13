from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List
import sqlite3
import csv
import io
import json
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd
from .ipm_client import IpmCredentials, IpmSoapClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

DB_PATH = Path(__file__).resolve().parents[1] / "lumine_nfse.db"
XML_DIR = Path(__file__).resolve().parents[1] / "storage" / "xml"
PDF_DIR = Path(__file__).resolve().parents[1] / "storage" / "pdf"
XML_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)

SERVICE_CODE = "10902"
ISS_RATE = 0.02
IBGE_CODE = "4306403"
DEFAULT_QTY = 1.00
UNIT = "un"

app = FastAPI(title="Lumine NFS-e")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            username TEXT,
            password TEXT,
            municipal_registration TEXT,
            last_rps_number INTEGER DEFAULT 0,
            rps_series TEXT DEFAULT '1',
            simulation_mode INTEGER DEFAULT 1
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nfse_number TEXT,
            rps_number INTEGER NOT NULL,
            rps_series TEXT NOT NULL,
            lot_number TEXT NOT NULL,
            issue_date TEXT NOT NULL,
            competence TEXT NOT NULL,
            taker_document TEXT NOT NULL,
            taker_name TEXT NOT NULL,
            taker_email TEXT,
            status TEXT NOT NULL,
            service_description TEXT NOT NULL,
            gross_value REAL NOT NULL,
            iss_value REAL NOT NULL,
            cancel_reason TEXT,
            xml_path TEXT,
            pdf_path TEXT
        )
        """
    )
    cur.execute("INSERT OR IGNORE INTO settings(id,last_rps_number,rps_series,simulation_mode) VALUES(1,0,'1',1)")
    conn.commit()
    conn.close()


class SettingsIn(BaseModel):
    username: str
    password: str
    municipal_registration: str
    last_rps_number: int
    rps_series: str = "1"
    simulation_mode: bool = True


class CancelInput(BaseModel):
    reason: str


class IssueRow(BaseModel):
    document: str
    name: str
    address: str
    city: str
    uf: str
    cep: str
    email: str
    description: str
    gross_value: float
    competence: str


class BatchIssueInput(BaseModel):
    rows: List[IssueRow]


def valid_doc(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return len(digits) in (11, 14)


def next_rps_numbers(count: int):
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("SELECT last_rps_number, rps_series FROM settings WHERE id = 1").fetchone()
    start = row["last_rps_number"] + 1
    end = row["last_rps_number"] + count
    cur.execute("UPDATE settings SET last_rps_number = ? WHERE id = 1", (end,))
    conn.commit()
    conn.close()
    return list(range(start, end + 1)), row["rps_series"]


def make_xml(payload: dict) -> str:
    root = ET.Element("NFSe")
    for key, value in payload.items():
        child = ET.SubElement(root, key)
        child.text = str(value)
    return ET.tostring(root, encoding="unicode")


def make_pdf(path: Path, data: dict):
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    c.setFont("Helvetica-Bold", 14)
    c.drawString(30, y, "DANFSe - Lumine Entretenimento")
    y -= 30
    c.setFont("Helvetica", 10)
    for k, v in data.items():
        c.drawString(30, y, f"{k}: {v}")
        y -= 18
    c.save()


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/settings")
def get_settings():
    conn = get_conn()
    row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    conn.close()
    return dict(row)


@app.post("/api/settings")
def save_settings(data: SettingsIn):
    conn = get_conn()
    conn.execute(
        """
        UPDATE settings
        SET username=?, password=?, municipal_registration=?, last_rps_number=?, rps_series=?, simulation_mode=?
        WHERE id = 1
        """,
        (data.username, data.password, data.municipal_registration, data.last_rps_number, data.rps_series, int(data.simulation_mode)),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/import")
async def import_sheet(file: UploadFile = File(...)):
    content = await file.read()
    rows = []
    if file.filename.lower().endswith(".csv"):
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
        rows = list(reader)
    elif file.filename.lower().endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(content))
        rows = df.to_dict(orient="records")
    else:
        raise HTTPException(400, "Formato não suportado")

    errors = []
    normalized = []
    required = ["CNPJ/CPF", "Razão Social", "Endereço", "Município", "UF", "CEP", "E-mail", "Descrição do serviço", "Valor bruto do serviço", "Competência"]
    for i, row in enumerate(rows, start=1):
        miss = [k for k in required if k not in row or pd.isna(row[k]) or str(row[k]).strip() == ""]
        if miss:
            errors.append({"line": i, "error": f"Campos ausentes: {', '.join(miss)}"})
            continue
        doc = str(row["CNPJ/CPF"])
        if not valid_doc(doc):
            errors.append({"line": i, "error": "CNPJ/CPF inválido"})
            continue
        normalized.append({
            "document": doc,
            "name": str(row["Razão Social"]),
            "address": str(row["Endereço"]),
            "city": str(row["Município"]),
            "uf": str(row["UF"]),
            "cep": str(row["CEP"]),
            "email": str(row["E-mail"]),
            "description": str(row["Descrição do serviço"]),
            "gross_value": float(row["Valor bruto do serviço"]),
            "competence": str(row["Competência"]),
        })
    return {"preview": normalized, "errors": errors}


@app.post("/api/issue")
def issue_batch(payload: BatchIssueInput):
    if len(payload.rows) == 0:
        raise HTTPException(400, "Nenhuma linha para emissão")

    rps_numbers, series = next_rps_numbers(len(payload.rows))
    lot_number = datetime.now().strftime("%Y%m%d%H%M%S")
    conn = get_conn()
    settings = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    simulation = bool(settings["simulation_mode"])
    emitted = []

    ipm_client = IpmSoapClient() if not simulation else None
    cred = IpmCredentials(settings["username"] or "", settings["password"] or "", settings["municipal_registration"] or "")

    for idx, row in enumerate(payload.rows):
        rps = rps_numbers[idx]
        nfse = f"NF{datetime.now().strftime('%y%m%d')}{rps:06d}"
        iss = round(row.gross_value * ISS_RATE, 2)
        payload_xml = {
            "MunicipioIBGE": IBGE_CODE,
            "CodigoServico": SERVICE_CODE,
            "AliquotaISS": ISS_RATE,
            "Quantidade": DEFAULT_QTY,
            "Unidade": UNIT,
            "RPS": rps,
            "Serie": series,
            "TomadorDocumento": row.document,
            "TomadorNome": row.name,
            "Descricao": row.description,
            "ValorBruto": row.gross_value,
            "ISS": iss,
        }

        xml_text = make_xml(payload_xml)
        xml_path = XML_DIR / f"{nfse}.xml"
        xml_path.write_text(xml_text, encoding="utf-8")

        pdf_path = PDF_DIR / f"{nfse}.pdf"
        make_pdf(pdf_path, {
            "NFS-e": nfse,
            "RPS": rps,
            "Tomador": row.name,
            "Documento": row.document,
            "Serviço": row.description,
            "Valor": f"R$ {row.gross_value:.2f}",
            "ISS (2%)": f"R$ {iss:.2f}",
            "Competência": row.competence,
        })

        if ipm_client:
            try:
                ipm_client.emitir_rps_lote(xml_text, cred)
            except Exception as exc:
                conn.close()
                raise HTTPException(502, f"Falha no webservice IPM: {exc}")

        conn.execute(
            """
            INSERT INTO invoices (
                nfse_number,rps_number,rps_series,lot_number,issue_date,competence,
                taker_document,taker_name,taker_email,status,service_description,
                gross_value,iss_value,xml_path,pdf_path
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                nfse,
                rps,
                series,
                lot_number,
                date.today().isoformat(),
                row.competence,
                row.document,
                row.name,
                row.email,
                "ativa",
                row.description,
                row.gross_value,
                iss,
                str(xml_path),
                str(pdf_path),
            ),
        )
        emitted.append({"nfse_number": nfse, "rps_number": rps})

    conn.commit()
    conn.close()
    return {"message": "Lote emitido", "lot_number": lot_number, "notes": emitted}


@app.get("/api/invoices")
def list_invoices(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    number: Optional[str] = None,
    document: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    clauses = []
    params = []
    if start_date:
        clauses.append("issue_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("issue_date <= ?")
        params.append(end_date)
    if min_value is not None:
        clauses.append("gross_value >= ?")
        params.append(min_value)
    if max_value is not None:
        clauses.append("gross_value <= ?")
        params.append(max_value)
    if number:
        clauses.append("nfse_number = ?")
        params.append(number)
    if document:
        clauses.append("taker_document LIKE ?")
        params.append(f"%{document}%")
    if status:
        clauses.append("status = ?")
        params.append(status)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    offset = (page - 1) * page_size

    conn = get_conn()
    total = conn.execute(f"SELECT COUNT(*) AS c FROM invoices {where}", params).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM invoices {where} ORDER BY id DESC LIMIT ? OFFSET ?",
        [*params, page_size, offset],
    ).fetchall()
    conn.close()
    return {"total": total, "items": [dict(r) for r in rows]}


@app.post("/api/invoices/{invoice_id}/cancel")
def cancel_invoice(invoice_id: int, data: CancelInput):
    conn = get_conn()
    row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Nota não encontrada")
    if row["status"] == "cancelada":
        conn.close()
        raise HTTPException(400, "Nota já está cancelada")
    conn.execute("UPDATE invoices SET status='cancelada', cancel_reason=? WHERE id = ?", (data.reason, invoice_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/invoices/{invoice_id}/xml")
def download_xml(invoice_id: int):
    conn = get_conn()
    row = conn.execute("SELECT xml_path FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Nota não encontrada")
    return FileResponse(row["xml_path"], media_type="application/xml", filename=Path(row["xml_path"]).name)


@app.get("/api/invoices/{invoice_id}/pdf")
def download_pdf(invoice_id: int):
    conn = get_conn()
    row = conn.execute("SELECT pdf_path FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Nota não encontrada")
    return FileResponse(row["pdf_path"], media_type="application/pdf", filename=Path(row["pdf_path"]).name)


@app.post("/api/download-batch")
def download_batch(ids: List[int], kind: str = "xml"):
    conn = get_conn()
    placeholders = ",".join("?" * len(ids))
    field = "xml_path" if kind == "xml" else "pdf_path"
    rows = conn.execute(f"SELECT {field} as path FROM invoices WHERE id IN ({placeholders})", ids).fetchall()
    conn.close()

    zip_name = Path(__file__).resolve().parents[1] / "storage" / f"batch_{kind}_{uuid.uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zipf:
        for r in rows:
            p = Path(r["path"])
            if p.exists():
                zipf.write(p, arcname=p.name)
    return FileResponse(zip_name, media_type="application/zip", filename=zip_name.name)


@app.get("/api/reports/summary")
def report_summary(start_date: Optional[str] = None, end_date: Optional[str] = None):
    clauses = []
    params = []
    if start_date:
        clauses.append("issue_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("issue_date <= ?")
        params.append(end_date)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    conn = get_conn()
    totals = conn.execute(
        f"SELECT COUNT(*) AS notes, COALESCE(SUM(gross_value),0) AS gross, COALESCE(SUM(iss_value),0) AS iss FROM invoices {where}",
        params,
    ).fetchone()
    ranking = conn.execute(
        f"SELECT taker_name, COUNT(*) AS qty, SUM(gross_value) AS total FROM invoices {where} GROUP BY taker_name ORDER BY total DESC LIMIT 10",
        params,
    ).fetchall()
    by_comp = conn.execute(
        f"SELECT competence, SUM(iss_value) AS iss FROM invoices {where} GROUP BY competence ORDER BY competence",
        params,
    ).fetchall()
    conn.close()
    return {
        "totals": dict(totals),
        "ranking": [dict(r) for r in ranking],
        "iss_by_competence": [dict(r) for r in by_comp],
    }


@app.get("/api/reports/export")
def export_report(format: str = "excel"):
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM invoices ORDER BY issue_date DESC").fetchall()]
    conn.close()
    out_dir = Path(__file__).resolve().parents[1] / "storage"

    if format == "excel":
        output = out_dir / "relatorio_nfse.xlsx"
        pd.DataFrame(rows).to_excel(output, index=False)
        return FileResponse(output, filename=output.name)

    if format == "pdf":
        output = out_dir / "relatorio_nfse.pdf"
        c = canvas.Canvas(str(output), pagesize=A4)
        y = 800
        c.setFont("Helvetica-Bold", 12)
        c.drawString(30, y, "Relatório NFS-e")
        y -= 25
        c.setFont("Helvetica", 9)
        for row in rows[:35]:
            c.drawString(30, y, f"{row['nfse_number']} | {row['taker_name']} | R$ {row['gross_value']:.2f} | {row['status']}")
            y -= 16
            if y < 40:
                c.showPage()
                y = 800
        c.save()
        return FileResponse(output, filename=output.name)

    raise HTTPException(400, "Formato inválido")
