# mongodb_manager.py
import os
import json
import tempfile
import openpyxl
import pdfplumber
import docx
import re
import traceback
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
import streamlit as st
from groq import Groq

# -------------------------
# CONFIGURATION & API SETUP
# -------------------------
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")

if not GROQ_API_KEY:
    st.error("🚨 FATAL ERROR: GROQ_API_KEY not set in environment variables.")
    st.stop()

if not MONGODB_URI:
    st.error("🚨 FATAL ERROR: MONGODB_URI not set in environment variables.")
    st.stop()

client = Groq(api_key=GROQ_API_KEY)
GROQ_MODEL = "llama-3.1-8b-instant"


# -------------------------
# MongoDB Database Manager
# -------------------------
class DatabaseManager:
    """Handles connection and CRUD operations for MongoDB."""

    def __init__(self, uri):
        self.client = self.init_connection(uri)
        self.db = self.client.get_default_database() if self.client else None

    @st.cache_resource(ttl=3600)
    def init_connection(_self, mongo_uri):
        try:
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5500)
            client.admin.command("ping")
            client.get_default_database()
            return client
        except Exception as e:
            st.error(f"❌ MongoDB Connection Error: {e}")
            return None

    def is_connected(self):
        return self.client is not None and self.db is not None

    # --- JD Management ---
    def save_jd(self, jd_data, user_role):
        if not self.is_connected():
            return None
        collection = self.db[f"{user_role}_jds"]
        jd_data["updated_at"] = datetime.utcnow()
        existing = collection.find_one({"name": jd_data["name"], "content": jd_data["content"]})
        if existing:
            collection.update_one({"_id": existing["_id"]}, {"$set": jd_data})
            return existing["_id"]
        jd_data["created_at"] = datetime.utcnow()
        return collection.insert_one(jd_data).inserted_id

    def get_jds(self, user_role):
        if not self.is_connected():
            return []
        collection = self.db[f"{user_role}_jds"]
        items = list(collection.find({}).sort("created_at", -1))
        for i in items:
            i["_id"] = str(i["_id"])
        return items

    # --- Resume Management ---
    def save_resume(self, resume_data):
        if not self.is_connected():
            return None
        col = self.db["admin_resumes"]
        resume_data["updated_at"] = datetime.utcnow()
        resume_data.setdefault("status", "Pending")
        existing = col.find_one({"name": resume_data["name"]})
        if existing:
            col.update_one({"_id": existing["_id"]}, {"$set": resume_data})
            return existing["_id"]
        resume_data["created_at"] = datetime.utcnow()
        return col.insert_one(resume_data).inserted_id

    def get_resumes(self):
        if not self.is_connected():
            return []
        col = self.db["admin_resumes"]
        items = list(col.find({}).sort("created_at", -1))
        for i in items:
            i["_id"] = str(i["_id"])
            i.setdefault("status", "Pending")
        return items

    # --- Vendor Management ---
    def save_vendor(self, vendor_data):
        if not self.is_connected():
            return None
        col = self.db["vendors"]
        vendor_data["updated_at"] = datetime.utcnow()
        vendor_data.setdefault("status", "Pending")
        existing = col.find_one({"name": vendor_data["name"]})
        if existing:
            col.update_one({"_id": existing["_id"]}, {"$set": vendor_data})
            return existing["_id"]
        vendor_data["created_at"] = datetime.utcnow()
        return col.insert_one(vendor_data).inserted_id

    def get_vendors(self):
        if not self.is_connected():
            return []
        col = self.db["vendors"]
        items = list(col.find({}).sort("created_at", -1))
        for i in items:
            i["_id"] = str(i["_id"])
            i.setdefault("status", "Pending")
        return items

    # --- Match Results ---
    def save_match_result(self, data, role):
        if not self.is_connected():
            return None
        data["created_at"] = datetime.utcnow()
        return self.db[f"{role}_match_results"].insert_one(data).inserted_id

    def get_match_results(self, role):
        if not self.is_connected():
            return []
        results = list(self.db[f"{role}_match_results"].find({}).sort("created_at", -1).limit(50))
        for r in results:
            r["_id"] = str(r["_id"])
            if "created_at" in r:
                r["created_at_str"] = r["created_at"].strftime("%Y-%m-%d %H:%M")
        return results

    # --- Metrics ---
    def get_platform_metrics(self):
        if not self.is_connected():
            return dict.fromkeys(
                ["total_candidates", "total_jds", "total_vendors", "no_of_applications", "no_of_social_media_posts"], 0
            )
        db = self.db
        return {
            "total_candidates": db["admin_resumes"].count_documents({}),
            "total_jds": db["admin_jds"].count_documents({}) + db["candidate_jds"].count_documents({}),
            "total_vendors": db["vendors"].count_documents({}),
            "no_of_applications": db["admin_match_results"].count_documents({})
            + db["candidate_match_results"].count_documents({}),
            "no_of_social_media_posts": db["platform_metrics"].find_one({"_id": "social_media_counter"}, {"count": 1})
            or 0,
        }

    def update_social_media_posts_count(self, delta):
        if not self.is_connected():
            return 0
        col = self.db["platform_metrics"]
        result = col.find_one_and_update(
            {"_id": "social_media_counter"},
            {"$inc": {"count": delta}, "$set": {"updated_at": datetime.utcnow()}},
            upsert=True,
            return_document="after",
        )
        if result and result["count"] < 0:
            col.update_one({"_id": "social_media_counter"}, {"$set": {"count": 0}})
            return 0
        return result.get("count", 0)

    def clear_all_data(self):
        if not self.is_connected():
            return
        for col in [
            "admin_jds",
            "candidate_jds",
            "admin_resumes",
            "admin_match_results",
            "candidate_match_results",
            "vendors",
            "platform_metrics",
        ]:
            self.db[col].drop()

