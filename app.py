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

C_PORT = 8000

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


@app.route('/api/convos/random', methods=['GET'])
def get_convos():
    # gets 20 random conversations

    # Get pagination parameters from the query string, defaulting to page 1 and 10 results per page
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    convos_pages = Conversation.query.order_by(func.random()).limit(20).paginate(page=page, per_page=per_page, error_out=False)
    conversations = convos_pages.items

    return jsonify({
        "conversations": [
            {
                "id": conversation.id,
                "user_id": conversation.user_id,
                "start_date": conversation.start_date,
                "last_update": conversation.last_update
            }
            for conversation in conversations
        ],
        "page": convos_pages.page,
        "per_page": convos_pages.per_page,
        "total_pages": convos_pages.pages,
        "total_items": convos_pages.total,
    }
    ), 200

@app.route('/api/convos/user/<int:user_id>', methods=['GET'])
def get_convos_by_user_id(user_id):
    # user_id = request.args.get('userId')  # Retrieve the query parameter `userId`
    if user_id is None:
        return jsonify({"error": "userId is required"}), 400

    # Get pagination parameters from the query string, defaulting to page 1 and 10 results per page
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    convos_pages = Conversation.query.filter_by(user_id = user_id).paginate(page=page, per_page=per_page, error_out=False)

    conversations = convos_pages.items
    return jsonify({
        "conversations" : [
            {
                "id": conversation.id,
                "user_id": conversation.user_id,
                "start_date": conversation.start_date,
                "last_update": conversation.last_update
            }
            for conversation in conversations
        ],
        "page": convos_pages.page,
        "per_page": convos_pages.per_page,
        "total_pages": convos_pages.pages,
        "total_items": convos_pages.total,
        }
    ), 200




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=C_PORT)