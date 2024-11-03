import logging
import os
from datetime import timezone
from enum import Enum

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql.expression import func
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)
app.config['DEBUG'] = True

C_PORT = 5000

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://admin:lGrBWwcZJS10NwFBByTK@convos-db.c1ytbjumgtbu.us-east-1.rds.amazonaws.com:3306/conversation_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

class SenderType(Enum):
    user = 'user'
    ai = 'ai'

class Conversation(db.Model):
    __tablename__ = 'conversation'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.DateTime(timezone=True), default=func.now(), nullable=False)
    last_update = db.Column(db.DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)
    content_id = db.Column(db.Integer, nullable=False)
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

def add_links(response_data, endpoint, **params):
    """Add HATEOAS links to response"""
    base_url = "/api/convos"
    
    if endpoint == 'create':
        conversation = response_data.get('conversation', {})
        conv_id = conversation.get('id')
        response_data['_links'] = {
            'self': base_url,
            'reply': f"{base_url}/{conv_id}/reply",
            'delete': f"{base_url}/{conv_id}"
        }
    
    elif endpoint == 'list':
        response_data['_links'] = {
            'self': f"{base_url}?user_id={params.get('user_id')}",
            'create': base_url
        }
    
    elif endpoint == 'reply':
        conv_id = params.get('conversation_id')
        response_data['_links'] = {
            'self': f"{base_url}/{conv_id}/reply",
            'conversation': f"{base_url}/{conv_id}"
        }
    
    elif endpoint == 'delete':
        response_data['_links'] = {
            'conversations': base_url
        }
    
    return response_data


@app.route('/api/convos', methods=['POST'])
def create_convo():
    if not request.json:
        logging.warning("No data provided in request")
        return jsonify({"error": "No data provided"}), 400

    data = request.json
    user_id = data.get('user_id')
    content_id = data.get('content_id')
    content_chunk_id = data.get('content_chunk_id')

    if not user_id or not content_id:
        logging.warning("user_id and content_id are required")
        return jsonify({"error": "user_id and content_id are required"}), 400

    try:
        # Create conversation
        conversation = Conversation(user_id=user_id, content_id=content_id)
        db.session.add(conversation)
        db.session.flush()  # Flush to get the conversation ID
        db.session.commit()

        # Nudge gnosis-influencer to update the conversation
        influencer_response = requests.post(
            'http://localhost:5012/api/message/ai',
            json={'conversation_id': conversation.id, 'content_chunk_id': content_chunk_id}
            # Notice the inclusion of chunk_id, makes it so that it has a chunk to start the conversation
        )

        if influencer_response.status_code not in [200, 202]:
            logging.warning(f"gnosis-influencer responded with status code {influencer_response.status_code}")

        logging.info(f"Conversation created successfully with ID: {conversation.id}")
        response_data = {
            'message': 'Conversation created successfully',
            'conversation_id': conversation.id
        }
        return jsonify(response_data), 201

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
        response_data = {
            "conversations": [conv.to_dict() for conv in conversations]
        }
        return jsonify(add_links(response_data, 'list', user_id=user_id)), 200

    except Exception as e:
        logging.error(f"Error fetching conversations: {e}")
        return jsonify({"error": "Failed to fetch conversations"}), 500

# Get a conversation by id
@app.route('/api/convos/<int:conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    try:
        conversation = db.session.get(Conversation, conversation_id)
        if not conversation:
            logging.warning(f"Conversation not found: {conversation_id}")
            return jsonify({"error": "Conversation not found"}), 404
        return jsonify(conversation.to_dict()), 200
    except Exception as e:
        logging.error(f"Error fetching conversation: {e}")
        return jsonify({"error": "Failed to fetch conversation"}), 500

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
        db.session.flush()
        db.session.commit()
        
        # Update conversation last_update
        conversation.last_update = func.now()
        
        db.session.commit()

        # Nudge the influencer api with the conversation_id to get a reply
        influencer_response = requests.post(
            'http://localhost:5012/api/message/ai',
            json={'conversation_id': conversation_id}
        )

        logging.info(f"Nudged influencer with status code: {influencer_response.status_code}")

        logging.info(f"Reply added successfully to conversation ID: {conversation_id}")
        response_data = {
            "message": "Reply added successfully",
            "conversation": conversation.to_dict()
        }
        return jsonify(add_links(response_data, 'reply', conversation_id=conversation_id)), 200

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
        response_data = {
            "message": f"Conversation {conversation_id} deleted successfully"
        }
        return jsonify(add_links(response_data, 'delete')), 200

    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting conversation: {e}")
        return jsonify({"error": "Failed to delete conversation"}), 500 

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=C_PORT)