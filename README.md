# Lumine NFS-e (Dois Irmãos/RS)

Aplicação fullstack para emissão e gestão de NFS-e da Lumine Entretenimento, com foco na integração com AtendeNet/IPM.

## Arquitetura

- **Backend**: FastAPI + SQLite (`backend/app/main.py`)
- **Frontend**: React + Tailwind + Vite (`frontend/src/main.jsx`)
- **Armazenamento local**: XMLs e PDFs em `backend/storage/`
- **Modo simulação local**: habilitado por configuração para testar emissão sem homologação

## Funcionalidades implementadas

1. **Configurações**
   - Usuário, senha, inscrição municipal
   - Último RPS e série
   - Modo simulação local

2. **Importação de planilha**
   - CSV e XLSX
   - Preview antes da emissão
   - Validação de obrigatórios e CNPJ/CPF

3. **Emissão em lote de NFS-e**
   - Geração de RPS incremental persistente
   - Geração de XML e DANFSe (PDF)
   - Persistência do histórico

4. **Consulta e cancelamento**
   - Listagem com status
   - Cancelamento individual com motivo
   - Download de XML/PDF por nota

5. **Relatórios**
   - Totais emitidos e ISS
   - Ranking por tomador
   - Exportação para Excel e PDF

## Como rodar

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

## Integração real com AtendeNet/IPM

O projeto está preparado com fluxo e dados necessários. Para ativar produção:

- Validar WSDL/SOAP XML exato da prefeitura (`https://nfse-doisirmaos.atende.net/`)
- Implementar autenticação com usuário/senha em envelope IPM
- Tratar códigos de erro IPM (ex.: E165, E500)
- Garantir liberação de RPS no portal (Autorização > Utilização de NFS-e > Liberar Acesso ao Usuário)

## Exemplo de planilha

Colunas obrigatórias:

- `CNPJ/CPF`
- `Razão Social`
- `Endereço`
- `Município`
- `UF`
- `CEP`
- `E-mail`
- `Descrição do serviço`
- `Valor bruto do serviço`
- `Competência`
