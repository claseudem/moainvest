from datetime import datetime, timedelta
import dukascopy_python
from dukascopy_python.instruments import INSTRUMENT_ETF_CFD_US_SPY_US_USD

start = datetime(2025, 1, 1)
end = datetime(2026, 10, 20)
instrument = INSTRUMENT_ETF_CFD_US_SPY_US_USD
interval = dukascopy_python.INTERVAL_MIN_1
offer_side = dukascopy_python.OFFER_SIDE_BID

df = dukascopy_python.fetch(
    instrument,
    interval,
    offer_side,
    start,
    end,
)

print(df)