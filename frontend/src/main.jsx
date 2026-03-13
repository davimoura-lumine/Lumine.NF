import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const API = 'http://127.0.0.1:8000/api';

function App() {
  const [tab, setTab] = useState('config');
  const [settings, setSettings] = useState({ username:'', password:'', municipal_registration:'', last_rps_number:0, rps_series:'1', simulation_mode:true });
  const [preview, setPreview] = useState([]);
  const [errors, setErrors] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [report, setReport] = useState(null);

  useEffect(() => { fetch(`${API}/settings`).then(r=>r.json()).then(setSettings); loadInvoices(); }, []);

  const saveSettings = async () => {
    await fetch(`${API}/settings`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(settings) });
    alert('Configurações salvas');
  };

  const loadInvoices = async () => {
    const data = await fetch(`${API}/invoices`).then(r=>r.json());
    setInvoices(data.items || []);
  };

  const importSheet = async (file) => {
    const fd = new FormData();
    fd.append('file', file);
    const data = await fetch(`${API}/import`, { method:'POST', body: fd }).then(r=>r.json());
    setPreview(data.preview || []);
    setErrors(data.errors || []);
  };

  const issueBatch = async () => {
    await fetch(`${API}/issue`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ rows: preview }) });
    alert('Lote emitido com sucesso');
    setPreview([]);
    await loadInvoices();
  };

  const cancelInvoice = async (id) => {
    const reason = prompt('Motivo do cancelamento:');
    if (!reason) return;
    await fetch(`${API}/invoices/${id}/cancel`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ reason }) });
    await loadInvoices();
  };

  const loadReport = async () => {
    const data = await fetch(`${API}/reports/summary`).then(r=>r.json());
    setReport(data);
  };

  return <div className="max-w-7xl mx-auto p-6 space-y-6">
    <h1 className="text-2xl font-bold">Lumine Entretenimento · Emissão de NFS-e</h1>
    <div className="flex gap-2 flex-wrap">
      {['config','import','consulta','relatorios'].map(t =>
        <button key={t} onClick={()=>setTab(t)} className={`px-4 py-2 rounded ${tab===t?'bg-blue-600 text-white':'bg-white border'}`}>{t}</button>
      )}
    </div>

    {tab==='config' && <section className="bg-white p-4 rounded shadow space-y-3">
      <h2 className="font-semibold">Configurações</h2>
      <div className="grid md:grid-cols-2 gap-3">
        {['username','password','municipal_registration','last_rps_number','rps_series'].map(k =>
          <input key={k} className="border rounded px-3 py-2" placeholder={k} type={k==='password'?'password':'text'} value={settings[k]} onChange={e=>setSettings({...settings,[k]:k==='last_rps_number'?Number(e.target.value):e.target.value})} />
        )}
      </div>
      <label className="flex items-center gap-2"><input type="checkbox" checked={settings.simulation_mode} onChange={e=>setSettings({...settings, simulation_mode:e.target.checked})}/>Modo simulação local</label>
      <button onClick={saveSettings} className="bg-blue-600 text-white px-4 py-2 rounded">Salvar</button>
    </section>}

    {tab==='import' && <section className="bg-white p-4 rounded shadow space-y-3">
      <h2 className="font-semibold">Importação de Planilha</h2>
      <input type="file" accept=".csv,.xlsx" onChange={e=>importSheet(e.target.files[0])} />
      {errors.length>0 && <div className="text-red-600 text-sm">{errors.map((e,i)=><div key={i}>Linha {e.line}: {e.error}</div>)}</div>}
      <div className="overflow-auto border rounded">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-200"><tr><th className="p-2">Documento</th><th className="p-2">Razão Social</th><th className="p-2">Valor</th><th className="p-2">Competência</th></tr></thead>
          <tbody>{preview.map((r,i)=><tr key={i} className="border-t"><td className="p-2">{r.document}</td><td className="p-2">{r.name}</td><td className="p-2">{r.gross_value}</td><td className="p-2">{r.competence}</td></tr>)}</tbody>
        </table>
      </div>
      {preview.length>0 && <button onClick={issueBatch} className="bg-emerald-600 text-white px-4 py-2 rounded">Emitir lote</button>}
    </section>}

    {tab==='consulta' && <section className="bg-white p-4 rounded shadow space-y-3">
      <h2 className="font-semibold">Consulta e Cancelamento de NFS-e</h2>
      <table className="min-w-full text-sm border rounded overflow-hidden">
        <thead className="bg-slate-200"><tr><th className="p-2">NFS-e</th><th className="p-2">Tomador</th><th className="p-2">Valor</th><th className="p-2">Status</th><th className="p-2">Ações</th></tr></thead>
        <tbody>{invoices.map((n)=><tr key={n.id} className="border-t"><td className="p-2">{n.nfse_number}</td><td className="p-2">{n.taker_name}</td><td className="p-2">R$ {n.gross_value}</td><td className="p-2">{n.status}</td><td className="p-2 space-x-2"><a className="text-blue-600" href={`${API}/invoices/${n.id}/xml`}>XML</a><a className="text-blue-600" href={`${API}/invoices/${n.id}/pdf`}>PDF</a>{n.status==='ativa' && <button className="text-red-600" onClick={()=>cancelInvoice(n.id)}>Cancelar</button>}</td></tr>)}</tbody>
      </table>
    </section>}

    {tab==='relatorios' && <section className="bg-white p-4 rounded shadow space-y-3">
      <h2 className="font-semibold">Relatórios</h2>
      <button onClick={loadReport} className="bg-blue-600 text-white px-4 py-2 rounded">Atualizar</button>
      {report && <div className="space-y-2 text-sm">
        <div>Total notas: {report.totals.notes}</div>
        <div>Total bruto: R$ {Number(report.totals.gross).toFixed(2)}</div>
        <div>Total ISS: R$ {Number(report.totals.iss).toFixed(2)}</div>
        <div className="font-semibold">Ranking tomadores</div>
        {report.ranking.map((r,i)=><div key={i}>{r.taker_name}: {r.qty} nota(s), R$ {Number(r.total).toFixed(2)}</div>)}
      </div>}
      <div className="space-x-2">
        <a href={`${API}/reports/export?format=excel`} className="text-blue-600">Exportar Excel</a>
        <a href={`${API}/reports/export?format=pdf`} className="text-blue-600">Exportar PDF</a>
      </div>
    </section>}
  </div>;
}

createRoot(document.getElementById('root')).render(<App />);
