"""
Seed script — Migrates existing data.json + email_settings.json
into Supabase Database tables (users, items, email_settings).

Usage:
  1. Set SUPABASE_URL and SUPABASE_KEY environment variables.
  2. Run the SQL in supabase_schema.sql in the Supabase SQL Editor first.
  3. Then run:  python scripts/seed_supabase.py

This is idempotent — it uses upserts so re-running won't duplicate data.
"""
import json
import os
import sys

# Allow importing from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Set SUPABASE_URL and SUPABASE_KEY environment variables first.")
    sys.exit(1)

client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---- Load local data ----
data_path = os.path.join(os.path.dirname(__file__), "..", "data.json")
email_path = os.path.join(os.path.dirname(__file__), "..", "email_settings.json")

with open(data_path, "r") as f:
    data = json.load(f)

# ---- Seed users ----
users = data.get("users", [])
print(f"Seeding {len(users)} users...")
for user in users:
    row = {
        "id":       user["id"],
        "name":     user["name"],
        "email":    user["email"],
        "password": user["password"],
        "is_admin": user.get("is_admin", False),
        "points":   user.get("points", 0),
    }
    client.table("users").upsert(row, on_conflict="id").execute()
    print(f"  ✓ {row['name']} ({row['email']})")

# ---- Seed items ----
items = data.get("items", [])
print(f"\nSeeding {len(items)} items...")
for item in items:
    row = {
        "id":                             item["id"],
        "title":                          item.get("title", ""),
        "category":                       item.get("category", ""),
        "location":                       item.get("location", ""),
        "date_found":                     item.get("date_found", ""),
        "description":                    item.get("description", ""),
        "status":                         item.get("status", "found"),
        "image":                          item.get("image"),
        "reported_by_id":                 item.get("reported_by_id", ""),
        "reported_by_name":               item.get("reported_by_name", ""),
        "reported_by_email":              item.get("reported_by_email", ""),
        "date_submitted":                 item.get("date_submitted", ""),
        "submitted_to":                   item.get("submitted_to", "self"),
        "submitted_department":           item.get("submitted_department", ""),
        "holder_contact":                 item.get("holder_contact", ""),
        "department_verification_status": item.get("department_verification_status", "not_required"),
        "department_verified_by":         item.get("department_verified_by", ""),
        "department_verified_at":         item.get("department_verified_at", ""),
        "claim_status":                   item.get("claim_status", "none"),
        "claim_requested_by":             item.get("claim_requested_by", ""),
        "claim_requested_at":             item.get("claim_requested_at", ""),
        "claim_description":              item.get("claim_description", ""),
        "claim_reviewed_by":              item.get("claim_reviewed_by", ""),
        "claim_reviewed_at":              item.get("claim_reviewed_at", ""),
        "claim_review_notes":             item.get("claim_review_notes", ""),
    }
    client.table("items").upsert(row, on_conflict="id").execute()
    print(f"  ✓ {row['title']} ({row['id']})")

# ---- Seed email settings ----
if os.path.exists(email_path):
    with open(email_path, "r") as f:
        email_settings = json.load(f)
    row = {
        "id":       "main",
        "sender":   email_settings.get("sender", ""),
        "password": email_settings.get("password", ""),
        "enabled":  email_settings.get("enabled", False),
    }
    client.table("email_settings").upsert(row, on_conflict="id").execute()
    print(f"\n✓ Email settings seeded (sender: {row['sender']})")

print("\n✅ Migration complete! All data is now in Supabase Database.")
