import numpy as np
import pandas as pd
from src.fbmc_model import get_core_fbmc_parameters
from src.market_coupler import clear_fbmc_market


def test_fbmc_parameters_integrity():
    ptdf, ram, max_exp, max_imp = get_core_fbmc_parameters()
    assert ptdf.shape == (3, 4)
    assert len(ram) == 3
    assert (max_exp > 0).all()
    assert (max_imp < 0).all()


def test_market_coupling_conservation_of_energy():
    timestamps = pd.date_range("2026-08-01", periods=24, freq="h")
    prices = np.random.uniform(40, 120, size=(24, 4))

    df = clear_fbmc_market(prices, timestamps)

    # Net position conservation: sum(NP) == 0 for all hours
    total_balance = (
        df["de_net_export_mw"] + 
        df["fr_net_export_mw"] + 
        df["at_net_export_mw"] + 
        df["nl_net_export_mw"]
    )
    assert np.allclose(total_balance, 0.0, atol=1e-1)


def test_cnec_limits_enforced():
    timestamps = pd.date_range("2026-08-01", periods=12, freq="h")
    prices = np.random.uniform(30, 140, size=(12, 4))

    df = clear_fbmc_market(prices, timestamps, ram_scale_factor=0.8)

    assert (df["cnec1_de_fr_loading_pct"] <= 100.1).all()
    assert (df["cnec2_de_nl_loading_pct"] <= 100.1).all()
    assert (df["cnec3_de_at_loading_pct"] <= 100.1).all()
