from dataclasses import dataclass
import requests


@dataclass
class IpmCredentials:
    username: str
    password: str
    municipal_registration: str


class IpmSoapClient:
    def __init__(self, base_url: str = "https://nfse-doisirmaos.atende.net/"):
        self.base_url = base_url.rstrip("/")

    def _envelope(self, body: str, cred: IpmCredentials) -> str:
        return f"""
<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\">
  <soapenv:Header/>
  <soapenv:Body>
    <Autenticacao>
      <Usuario>{cred.username}</Usuario>
      <Senha>{cred.password}</Senha>
      <InscricaoMunicipal>{cred.municipal_registration}</InscricaoMunicipal>
    </Autenticacao>
    {body}
  </soapenv:Body>
</soapenv:Envelope>
""".strip()

    def emitir_rps_lote(self, xml_lote: str, cred: IpmCredentials) -> str:
        payload = self._envelope(f"<EmitirLoteRps>{xml_lote}</EmitirLoteRps>", cred)
        response = requests.post(
            self.base_url,
            data=payload.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8"},
            timeout=30,
        )
        response.raise_for_status()
        return response.text
