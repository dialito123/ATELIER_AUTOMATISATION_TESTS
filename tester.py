import time
from datetime import datetime
import requests


# --- 1. CLIENT HTTP AVEC TIMEOUT ET RETRY ---
class ApiClient:

    def __init__(
        self,
        base_url: str = "https://api.frankfurter.app",
        timeout: float = 3.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, max_retries: int = 1, **kwargs):
        url = f"{self.base_url}{path}"
        retries = 0

        while retries <= max_retries:
            start_time = time.perf_counter()
            try:
                response = requests.request(
                    method=method, url=url, timeout=self.timeout, **kwargs
                )
                latency_ms = (time.perf_counter() - start_time) * 1000

                # Gestion backoff si rate limit (429)
                if response.status_code == 429 and retries < max_retries:
                    time.sleep(1.0)
                    retries += 1
                    continue

                is_json = "application/json" in response.headers.get(
                    "Content-Type", ""
                )
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "json": response.json() if is_json else None,
                    "latency_ms": round(latency_ms, 2),
                    "error": None,
                }
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ) as exc:
                latency_ms = (time.perf_counter() - start_time) * 1000
                retries += 1
                if retries > max_retries:
                    return {
                        "success": False,
                        "status_code": 0,
                        "headers": {},
                        "json": None,
                        "latency_ms": round(latency_ms, 2),
                        "error": str(exc),
                    }
                time.sleep(0.5)


# --- 2. LES 6 TESTS (CONTRAT + ROBUSTESSE) ---
def run_all_contract_tests(client: ApiClient) -> list[dict]:
    results = []

    # 1. Contrat nominal /latest
    res1 = client.request("GET", "/latest")
    p1 = (
        res1["status_code"] == 200
        and res1["json"]
        and isinstance(res1["json"].get("rates"), dict)
        and res1["json"].get("base") == "EUR"
    )
    results.append({
        "name": "GET /latest - Contrat 200 & Schéma",
        "status": "PASS" if p1 else "FAIL",
        "latency_ms": res1["latency_ms"],
        "details": (
            "Schéma conforme"
            if p1
            else f"Statut {res1['status_code']} inattendu"
        ),
    })

    # 2. Contrat liste des devises
    res2 = client.request("GET", "/currencies")
    p2 = res2["status_code"] == 200 and res2["json"] and "USD" in res2["json"]
    results.append({
        "name": "GET /currencies - Liste devises",
        "status": "PASS" if p2 else "FAIL",
        "latency_ms": res2["latency_ms"],
        "details": (
            "Devises retournées" if p2 else "Erreur de format devises"
        ),
    })

    # 3. Paramètres de devise
    res3 = client.request("GET", "/latest?from=USD")
    p3 = (
        res3["status_code"] == 200
        and res3["json"]
        and res3["json"].get("base") == "USD"
    )
    results.append({
        "name": "GET /latest?from=USD - Devise de base",
        "status": "PASS" if p3 else "FAIL",
        "latency_ms": res3["latency_ms"],
        "details": "Base USD validée" if p3 else "Base incorrecte",
    })

    # 4. Série chronologique
    res4 = client.request("GET", "/2024-01-01..2024-01-05")
    p4 = (
        res4["status_code"] == 200
        and res4["json"]
        and isinstance(res4["json"].get("rates"), dict)
    )
    results.append({
        "name": "GET /2024-01-01..2024-01-05 - Série temporelle",
        "status": "PASS" if p4 else "FAIL",
        "latency_ms": res4["latency_ms"],
        "details": (
            "Historique conforme" if p4 else "Erreur historique"
        ),
    })

    # 5. Robustesse : Symbole invalide (404 attendu)
    res5 = client.request("GET", "/latest?symbols=INVALIDE")
    p5 = res5["status_code"] == 404
    results.append({
        "name": "GET /latest?symbols=INVALIDE - 404 attendu",
        "status": "PASS" if p5 else "FAIL",
        "latency_ms": res5["latency_ms"],
        "details": (
            "Erreur 404 reçue"
            if p5
            else f"Code reçu : {res5['status_code']}"
        ),
    })

    # 6. Robustesse : Endpoint inexistant (404 attendu)
    res6 = client.request("GET", "/route_inconnue_404")
    p6 = res6["status_code"] == 404
    results.append({
        "name": "GET /route_inconnue_404 - 404 attendu",
        "status": "PASS" if p6 else "FAIL",
        "latency_ms": res6["latency_ms"],
        "details": (
            "Erreur 404 reçue"
            if p6
            else f"Code reçu : {res6['status_code']}"
        ),
    })

    return results


# --- 3. EXÉCUTEUR & CALCUL QoS ---
def execute_test_suite() -> dict:
    client = ApiClient()
    tests = run_all_contract_tests(client)

    latencies = sorted([t["latency_ms"] for t in tests])
    total = len(tests)
    passed = sum(1 for t in tests if t["status"] == "PASS")
    failed = total - passed

    avg_lat = sum(latencies) / total if total > 0 else 0
    p95_idx = int(round(0.95 * total)) - 1
    p95_lat = latencies[max(0, min(p95_idx, total - 1))] if total > 0 else 0

    return {
        "api": "Frankfurter",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "passed": passed,
            "failed": failed,
            "error_rate": round(failed / total, 3) if total > 0 else 0.0,
            "latency_ms_avg": round(avg_lat, 2),
            "latency_ms_p95": round(p95_lat, 2),
        },
        "tests": tests,
    }
