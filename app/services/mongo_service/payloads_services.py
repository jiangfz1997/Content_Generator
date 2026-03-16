from app.core.config import settings
from app.db.mongodb import db
import os,json

class PayloadsMongoService:
    def __init__(self):
        self.collection_name = "payloads"

    async def load_preset_payloads(self):
        presets_dir = settings.PAYLOADS_PATH
        collections = db.db[self.collection_name]
        ops = []

        for filename in os.listdir(presets_dir):
            if filename.endswith(".json"):

                with open(os.path.join(presets_dir, filename), 'r', encoding=settings.ENCODING) as f:
                    raw_data = json.load(f)

                    try:
                        payload_doc =
