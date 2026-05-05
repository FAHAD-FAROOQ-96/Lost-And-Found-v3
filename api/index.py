from app import app, setup_sample_data

# Seed initial sample users if data store is empty.
setup_sample_data()

handler = app