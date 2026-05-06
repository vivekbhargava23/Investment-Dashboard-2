from datetime import datetime

import streamlit as st

from app.domain.tax.models import TaxProfile
from app.services.valuation import compute_live_positions
from app.ui.cache_keys import transactions_signature
from app.ui.components.sell_simulator import render_sell_simulator
from app.ui.wiring import (
    get_fx_provider,
    get_price_provider,
    get_repository,
    get_tax_profile_repo,
)


@st.cache_data(ttl=60, show_spinner=False)
def _cached_live_positions(tx_sig: str):
    transactions = get_repository().load_all()
    return compute_live_positions(transactions, get_price_provider(), get_fx_provider())

def render() -> None:
    st.markdown("<h1>Simulator</h1>", unsafe_allow_html=True)
    
    repo = get_repository()
    transactions = repo.load_all()
    sig = transactions_signature(transactions)
    live_positions = _cached_live_positions(sig)
    
    tax_repo = get_tax_profile_repo()
    doc = tax_repo.load()
    profile = TaxProfile(filing_status=doc.filing_status)
    year = datetime.now().year
    yearly_inputs = doc.inputs_for_year(year)

    render_sell_simulator(
        transactions=transactions,
        live_positions=live_positions,
        profile=profile,
        yearly_inputs=yearly_inputs,
    )
