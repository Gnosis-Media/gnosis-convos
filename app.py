import logging
import os
from datetime import timezone

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy_utils import database_exists, create_database
from sqlalchemy.sql.expression import func, select
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

C_PORT = 5000

# Use the existing database
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://admin:Wfe._84ivN3UX4j.X2z!dfKnAiRA@content-database-1.c1qcm4w2sbne.us-east-1.rds.amazonaws.com:3306/conversation_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Conversation(db.Model):
    __tablename__ = 'conversation'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.DateTime(timezone=True), default=func.now(), nullable=False)
    last_update = db.Column(db.DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)
    reply = db.Column(db.String, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'start_date': self.start_date,
            'last_update': self.last_update,
            'reply': self.reply,
        }

@app.errorhandler(404)
def custom_404(error):
    # Check if the URL matches the expected pattern for conversation messages
    if request.path.startswith('/api/convos/') and request.path.endswith('/messages'):
        return jsonify({"error": "Invalid conversation ID. Please provide a valid integer ID."}), 404
    # Default 404 handler for other endpoints
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(400)
def custom_400(error):
    # Default 400 handler for other endpoints
    return jsonify({"error": "Bad Request"}), 400

@app.route('/api/convos/random', methods=['GET'])
def get_convos():
    # Get 10 random conversations
    conversations = Conversation.query.order_by(func.random()).limit(10)

    # If no conversation exists
    if len(conversations) == 0:
        return jsonify({"success": "No conversation found"}), 204

    # Return random conversations
    return jsonify({
        "conversations": [
            {
                "id": conversation.id,
                "user_id": conversation.user_id,
                "start_date": conversation.start_date,
                "last_update": conversation.last_update,
                "reply": conversation.reply
            }
            for conversation in conversations
        ],
    }), 200

@app.route('/api/convos', methods=['GET'])
def get_convos_by_user_id():
    # If userId is part of the request
    if 'userId' not in request.args:
        return jsonify({"error": "No userId in the request"}), 400

    # Get the query parameter `userId`
    user_id = request.args.get('userId')

    # if no input provided from userId, then return error
    if user_id is None:
        return jsonify({"error": "user_id is required"}), 400

    # if non-integer user_id provided, then return error
    try:
        user_id = int(user_id)
    except ValueError:
        return jsonify({"error": "user_id must be a valid integer"}), 400

    # Get pagination parameters from the query string, defaulting to page 1 and 10 results per page
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # Get all conversations made by user_id
    convos_pages = (Conversation.query.filter_by(user_id=user_id)
                    .order_by(Conversation.start_date.desc())
                    .paginate(page=page, per_page=per_page, error_out=False))

    conversations = convos_pages.items

    # No conversation found for user
    if len(conversations) == 0:
        return jsonify({"success": "No conversation found for user"}), 204

    # Return all conversations made by user_id in a page
    return jsonify({
        "conversations": [
            {
                "id": conversation.id,
                "user_id": conversation.user_id,
                "start_date": conversation.start_date,
                "last_update": conversation.last_update,
                "reply": conversation.reply,
            }
            for conversation in conversations
        ],
        "page": convos_pages.page,
        "per_page": convos_pages.per_page,
        "total_pages": convos_pages.pages,
        "total_items": convos_pages.total,
    }), 200

@app.route('/api/convos/<int:id>/messages', methods=['GET'])
def get_convos_by_id(id):
    # Fetch conversation by id
    conversation = Conversation.query.get(id=id)

    # Check if it exists
    if conversation is None:
        return jsonify({"error": f"No conversation found for id {id}"}), 404

    # Return conversation
    return jsonify({
        "conversations": [
            {
                "id": conversation.id,
                "user_id": conversation.user_id,
                "start_date": conversation.start_date,
                "last_update": conversation.last_update,
                "reply": conversation.reply
            }
        ],
    }), 200

@app.route('/api/convos/<int:id>', methods=['DELETE'])
def delete_convos_by_msg_id(id):
    # Get conversation by id
    conversation = Conversation.query.get(id=id)

    # Check if conversation exists
    if conversation is None:
        return jsonify({"error": f"No conversation found for id {id}"}), 404

    # Perform deletion of conversation
    db.session.delete(conversation)
    db.session.commit()

    return jsonify({"success": f"Conversation with id {id} was deleted successfully"}), 200

@app.route('/api/convos/<int:id>', methods=['PUT'])
def add_reply_to_conversation(id):
    # Check if 'reply' is provided in the request body
    if not request.json or 'reply' not in request.json:
        return jsonify({"error": "No reply provided"}), 400

    reply = request.json['reply']
    conversation = Conversation.query.get(id=id)

    # Check if conversation was found
    if conversation is None:
        return jsonify({"error": f"No conversation found for id {id}"}), 404

    # Adds reply to conversation
    try:
        conversation.reply = reply
        db.session.commit()
        logging.info(f"Added reply to conversation with id {id}")
    except Exception as e:
        logging.error(f"Failed to add reply to conversation with id {id}: {e}")
        return jsonify({"error": "Failed to add reply to conversation"}), 500

    # Updated conversation returned
    return jsonify({
        "message": f"Conversation with id {id} was updated successfully",
        "conversation": conversation.to_dict()
    }), 200

@app.route('/api/convos', methods=['POST'])
def create_convo():
    # Checks if 'conversation' is in the request
    if not request.json or 'conversation' not in request.json:
        return jsonify({"error": "No conversation provided"}), 400

    conversation_data = request.json['conversation']
    user_id = conversation_data.get('user_id')

    # Check if user_id exists
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    # Check if user_id is an integer
    try:
        user_id = int(user_id)
    except ValueError:
        return jsonify({"error": "user_id must be a valid integer"}), 400

    # Create conversation out of given information
    try:
        conversation = Conversation(
            user_id=user_id
        )
        db.session.add(conversation)
        db.session.commit()
        logging.info(f"Conversation saved with ID: {conversation.id}")
    except Exception as e:
        logging.error(f"Error while saving conversation: {e}")
        return jsonify({"error": "Failed to save conversation"}), 500

    # Return created conversation
    return jsonify({
        'message': 'Conversation successfully created',
        'conversation': conversation.to_dict(),
    }), 201

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=C_PORT)