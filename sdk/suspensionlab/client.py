import requests
from typing import Dict, Any, Optional

class SuspensionLabClient:
    """
    Python SDK Client for the SuspensionLab PRO API.
    
    Provides programmatic access to the physics simulation engines, 
    optimization algorithms, and Monte Carlo sensitivity sweeps.
    """
    
    def __init__(self, api_key: str, base_url: str = "http://localhost:8000"):
        """
        Initialize the SuspensionLab Client.
        
        :param api_key: Your secret API key starting with 'sk_'.
        :param base_url: The base URL of the API. Defaults to localhost for dev.
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        })
        
    def simulate_quarter_car(self, params: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a Quarter Car simulation.
        
        :param params: Dictionary containing k_s, c, m_s, m_u, k_t, etc.
        :param profile: Dictionary containing profile_type, duration, etc.
        :return: JSON response with comfort and grip metrics.
        """
        url = f"{self.base_url}/api/v1/simulate/quarter"
        payload = {"params": params, "profile": profile}
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        return response.json()
        
    def run_monte_carlo(self, params: Dict[str, Any], profile: Dict[str, Any], iterations: int = 500, tolerance_pct: float = 5.0) -> Dict[str, Any]:
        """
        Run a Monte Carlo parameter sweep on the Quarter Car model.
        
        :param params: Base suspension parameters.
        :param profile: Road profile configuration.
        :param iterations: Number of simulations to run.
        :param tolerance_pct: Standard deviation as a percentage of the base value.
        :return: JSON response containing statistical confidence intervals.
        """
        url = f"{self.base_url}/api/v1/simulate/monte-carlo"
        payload = {
            "params": params, 
            "profile": profile, 
            "iterations": iterations, 
            "tolerance_pct": tolerance_pct
        }
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        return response.json()
