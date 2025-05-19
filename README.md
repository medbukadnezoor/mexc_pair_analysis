# MEXC Perpetual Pairs Analysis Web Application

A cloud-native FastAPI + Bootstrap SPA for analyzing and exporting uncorrelated, high-volume perpetual trading pairs on MEXC. See live endpoints after deployment.

## Features
- Real-time autocomplete for valid MEXC perpetual symbols
- Analyze and rank top 20 uncorrelated pairs by volume
- Fallback to CoinGecko/CoinMarketCap if MEXC fails
- PDF/CSV export
- Robust error handling and cloud-native deployment

## Quick Start
All deployment, testing, and running is fully automated in the cloud. See `.github/workflows/ci.yml` for details.

## Live URLs
- Dev: _TBD_
- Staging: _TBD_
- Production: _TBD_

## API Endpoints
- `GET /pairs` — List all available perpetual symbols (autocomplete)
- `POST /analyze` — Analyze correlations for a given base symbol
- `GET /export/csv` — Download CSV of results

## Security
API keys are stored as cloud environment variables and never logged or exposed.

---
# Trigger redeploy
