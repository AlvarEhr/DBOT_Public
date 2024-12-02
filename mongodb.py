from pymongo import MongoClient
import os
from dotenv import load_dotenv
load_dotenv()

class MongoDBWrapper:
    def __init__(self):
        connection_string = os.environ['CONNECTION_STRING']
        database_name = 'DBOT'
        collection_name = 'DBOT_Keys'
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.collection = self.db[collection_name]

    def keys(self):
        return [doc['key'] for doc in self.collection.find({}, {"_id": 0, "key": 1})]

    def __getitem__(self, key):
        document = self.collection.find_one({"key": key}, {"_id": 0, "value": 1})
        return document['value'] if document else None

    def __setitem__(self, key, value):
        self.collection.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)

    def __delitem__(self, key):
        self.collection.delete_one({"key": key})

    def get(self, key, default=None):
        return self[key] if self[key] is not None else default

db = MongoDBWrapper()