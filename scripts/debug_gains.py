from app.data.repository import load_portfolio
from app.services.price_service import get_currency, convert_to_eur

portfolio = load_portfolio()
for pos in portfolio.positions:
    print(f"Ticker: {pos.ticker}")
    print(f"  Transactions: {len(pos.transactions)}")
    replayed = pos.realised_disposals
    print(f"  Realised Disposals: {len(replayed)}")
    for d in replayed:
        print(f"    ID: {d.sell_transaction_id}, Gain: {d.total_gain}")
