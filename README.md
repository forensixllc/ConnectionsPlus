# Pulte +

A forensic subdomain analysis tool that maps IP and CNAME overlaps between PulteGroup and thousands of other domains.

## Try it live
[Streamlit Cloud Deployment](https://your-app.streamlit.app)

## How it works
- The app queries a pre‑built SQLite database (315 MB) that contains over 1.1 million rows of subdomain overlap data.
- You can search by:
  - **Hub Domain** (e.g., any Pulte subdomain)
  - **Risk Category** (e.g., "Money Laundering", "Inmate Tracking / Deed Fraud")
  - **Overlap Domain** (e.g., "relativity.com")

## Data source
The database is built from public subdomain scans and forensic analysis. It is hosted externally and downloaded on first run.

## Deployment
1. Fork this repo.
2. Set the `DB_URL` environment variable (or edit `app.py` with your own public database URL).
3. Deploy on Streamlit Cloud.

## License
MIT