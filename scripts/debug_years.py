from app.data.repository import load_portfolio
from app.services.price_service import get_currency, convert_to_eur

portfolio = load_portfolio()
for pos in portfolio.positions:
    replayed = pos.realised_disposals
    if replayed:
        print(f"Ticker: {pos.ticker}")
        for d in replayed:
            print(f"    Date: {d.trade_date}, Gain: {d.total_gain}")
