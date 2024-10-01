import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy_utils import database_exists, create_database
from  sqlalchemy.sql.expression import func, select
# import random

app = Flask(__name__)

# Use the existing database
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://admin:Wfe._84ivN3UX4j.X2z!dfKnAiRA@content-database-1.c1qcm4w2sbne.us-east-1.rds.amazonaws.com:3306/user_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Conversation(db.Model):
    __tablename__ = 'conversation'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    last_date = db.Column(db.DateTime, nullable=False)


@app.route('/api/get_convos', methods=['GET'])
def get_convos():
    # gets 20 random conversations
    conversations = Conversation.order_by(func.rand()).limit(10)
    return jsonify(
        [{"id": conversations.id, "user_id": conversations.user_id, "start_date": conversations.start} for conversation
         in conversations]), 200




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)