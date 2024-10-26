import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy_utils import database_exists, create_database
from  sqlalchemy.sql.expression import func, select
from flask_cors import CORS
# import random
from flask_cors import CORS
# CORS
app = Flask(__name__)
CORS(app)

C_PORT = 5000

# Use the existing database
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://admin:Wfe._84ivN3UX4j.X2z!dfKnAiRA@content-database-1.c1qcm4w2sbne.us-east-1.rds.amazonaws.com:3306/conversation_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Conversation(db.Model):
    __tablename__ = 'conversation'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    last_update = db.Column(db.DateTime, nullable=False)


@app.route('/api/convos', methods=['GET'])
def get_convos():
    # gets 20 random conversations
    # conversations = Conversation.query.order_by(func.random()).limit(20)
    conversations = Conversation.query.order_by(func.random()).limit(20)
    return jsonify(
        [{"id": conversation.id, "user_id": conversation.user_id, "start_date": conversation.start_date, "last_update": conversation.last_update} for conversation
         in conversations]), 200

@app.route('/api/convos?userId={id}', methods=['GET'])
def get_convos_by_id(id):
    conversations = Conversation.query.filter_by(id = id).all()
    return jsonify(
        [{"id": conversation.id, "user_id": conversation.user_id, "start_date": conversation.start_date, "last_update": conversation.last_update} for conversation
         in conversations]), 200 




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=C_PORT)