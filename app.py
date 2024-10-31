import logging
import os
from datetime import timezone
from enum import Enum

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql.expression import func
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

C_PORT = 5000

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://admin:lGrBWwcZJS10NwFBByTK@convos-db.c1ytbjumgtbu.us-east-1.rds.amazonaws.com:3306/conversation_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S', filename='app.log')

class SenderType(Enum):
    user = 'user'
    ai = 'ai'

class Conversation(db.Model):
    __tablename__ = 'conversation'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.DateTime(timezone=True), default=func.now(), nullable=False)
    last_update = db.Column(db.DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)
    messages = db.relationship('Message', backref='conversation', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_messages=True):
        data = {
            'id': self.id,
            'user_id': self.user_id,
            'start_date': self.start_date,
            'last_update': self.last_update,
        }
        if include_messages:
            data['messages'] = [message.to_dict() for message in self.messages]
        return data

class Message(db.Model):
    __tablename__ = 'message'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    sender = db.Column(db.Enum(SenderType), nullable=False)
    content_chunk_id = db.Column(db.Integer, nullable=True)
    message_text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), default=func.now(), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender': self.sender.value,
            'content_chunk_id': self.content_chunk_id,
            'message_text': self.message_text,
            'timestamp': self.timestamp
        }

@app.route('/api/convos', methods=['POST'])
def create_convo():
    if not request.json:
        logging.warning("No data provided in request")
        return jsonify({"error": "No data provided"}), 400

    data = request.json
    user_id = data.get('user_id')
    initial_message = data.get('message')

    if not user_id or not initial_message:
        logging.warning("user_id and message are required")
        return jsonify({"error": "user_id and message are required"}), 400

    try:
        # Create conversation
        conversation = Conversation(user_id=user_id)
        db.session.add(conversation)
        db.session.flush()  # Flush to get the conversation ID

        # Create initial AI message
        message = Message(
            conversation_id=conversation.id,
            sender=SenderType.ai,
            message_text=initial_message
        )
        db.session.add(message)
        db.session.commit()

        logging.info(f"Conversation created successfully with ID: {conversation.id}")
        return jsonify({
            'message': 'Conversation created successfully',
            'conversation': conversation.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error creating conversation: {e}")
        return jsonify({"error": "Failed to create conversation"}), 500

@app.route('/api/convos', methods=['GET'])
def get_convos():
    user_id = request.args.get('user_id')
    limit = request.args.get('limit', 10, type=int)
    random = request.args.get('random', 'false').lower() == 'true'

    if not user_id:
        logging.warning("user_id is required")
        return jsonify({"error": "user_id is required"}), 400

    try:
        query = Conversation.query.filter_by(user_id=user_id)
        
        if random:
            conversations = query.order_by(func.random()).limit(limit).all()
        else:
            conversations = query.order_by(Conversation.id.desc()).limit(limit).all()

        logging.info(f"Fetched {len(conversations)} conversations for user_id: {user_id}")
        return jsonify({
            "conversations": [conv.to_dict() for conv in conversations]
        }), 200

    except Exception as e:
        logging.error(f"Error fetching conversations: {e}")
        return jsonify({"error": "Failed to fetch conversations"}), 500

@app.route('/api/convos/<int:conversation_id>/reply', methods=['PUT'])
def add_reply(conversation_id):  # Add the parameter here
    if not request.json or 'message' not in request.json:
        logging.warning("message is required")
        return jsonify({"error": "message is required"}), 400

    message_text = request.json['message']

    try:
        conversation = db.session.get(Conversation, conversation_id)
        if not conversation:
            logging.warning(f"Conversation not found: {conversation_id}")
            return jsonify({"error": "Conversation not found"}), 404

        message = Message(
            conversation_id=conversation_id,
            sender=SenderType.user,
            message_text=message_text
        )
        db.session.add(message)
        
        # Update conversation last_update
        conversation.last_update = func.now()
        
        db.session.commit()

        logging.info(f"Reply added successfully to conversation ID: {conversation_id}")
        return jsonify({
            "message": "Reply added successfully",
            "conversation": conversation.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error adding reply: {e}")
        return jsonify({"error": "Failed to add reply"}), 500

@app.route('/api/convos/<int:conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    try:
        conversation = db.session.get(Conversation, conversation_id)
        if not conversation:
            logging.warning(f"Conversation not found for deletion: {conversation_id}")
            return jsonify({"error": "Conversation not found"}), 404

        db.session.delete(conversation)
        db.session.commit()

        logging.info(f"Conversation {conversation_id} deleted successfully")
        return jsonify({
            "message": f"Conversation {conversation_id} deleted successfully"
        }), 200

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting conversation: {e}")
        return jsonify({"error": "Failed to delete conversation"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=C_PORT)