import logging
import os
from datetime import timezone
from enum import Enum
import time

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql.expression import func
from sqlalchemy.types import Numeric  
from flask_cors import CORS
import requests
import subprocess
import random
from secrets_manager import get_service_secrets
from base64 import b64encode, b64decode
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)
app.config['DEBUG'] = True

secrets = get_service_secrets('gnosis-convos')

# Set up the Influencer API URL
INFLUENCER_API_URL = secrets.get('INFLUENCER_API_URL')
PROFILES_API_URL = secrets.get('PROFILES_API_URL')
CONTENT_PROCESSOR_API_URL = secrets.get('CONTENT_PROCESSOR_API_URL')
CONVERSATION_API_URL = secrets.get('CONVERSATION_API_URL', 'http://localhost:5000')

C_PORT = int(secrets.get('PORT', 5000))

# Database configuration
SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{secrets['MYSQL_USER']}:{secrets['MYSQL_PASSWORD_CONVOS']}"
    f"@{secrets['MYSQL_HOST']}:{secrets['MYSQL_PORT']}/{secrets['MYSQL_DATABASE']}"
)
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

class SenderType(Enum):
    user = 'user'
    ai = 'ai'

def encode_cursor(cursor_dict):
    """Encode cursor dictionary to base64 string"""
    return b64encode(json.dumps(cursor_dict).encode()).decode()

def decode_cursor(cursor_str):
    """Decode base64 cursor string to dictionary"""
    try:
        return json.loads(b64decode(cursor_str).decode())
    except:
        return None
    

class Conversation(db.Model):
    __tablename__ = 'conversation'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.DateTime(timezone=True), default=func.now(), nullable=False)
    last_update = db.Column(db.DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)
    content_id = db.Column(db.Integer, nullable=False)
    score = db.Column(Numeric(10, 4), default=0.0, nullable=True)
    messages = db.relationship('Message', backref='conversation', lazy=True, cascade='all, delete-orphan')
    
    def calculate_base_score(self):
        """Calculate base score from message length and age"""
        # Get total length score (0 to 1)
        total_length = sum(len(message.message_text) for message in self.messages)
        length_score = min(total_length / 1000, 1.0)  # Cap at 1.0
        
        # Get age score (1.0 for new, approaching 0 for old)
        now = datetime.now(timezone.utc).replace(tzinfo=None)        
        
        # Handle case where start_date is None or naive
        if self.start_date is None:
            self.start_date = now
            db.session.commit()
        
        # logging.info(f"Start date: {self.start_date}")
        # logging.info(f"Now: {now}")

        age_in_hours = (now - self.start_date).total_seconds() / 3600
        age_score = 1.0 / (1.0 + age_in_hours/24)  # Decay over days
        
        # Combine scores with weights
        return (length_score * 0.3) + (age_score * 0.7)

    def update_score(self, randomness_factor=0.1):
        """Update score with base calculation plus controlled randomness"""
        base_score = self.calculate_base_score()
        random_adjustment = (random.random() * 2 - 1) * randomness_factor  # -0.1 to +0.1
        self.score = base_score + random_adjustment

    @classmethod
    def shuffle_scores(cls, user_id, volatility=0.3):
        """Shuffle scores for all user's conversations with controlled volatility"""
        # Get all conversations in a single query with only necessary columns
        conversations = cls.query.filter_by(user_id=user_id).all()
        
        # logging.info(f"Conversations: {conversations}")

        # Prepare bulk updates
        max_id = max(conv.id for conv in conversations)
        updates = []
        
        logging.info("Starting score calculation")
        # Calculate all scores in memory
        for conv in conversations:
            # Base score from ID (0.1 to 1.0) - newer conversations get higher base scores
            base_score = (1 - volatility) * (conv.id / max_id)
            
            # Add significant randomness
            random_value = random.gauss(0, volatility)
            new_score = base_score + random_value * volatility
            
            # Ensure score stays within reasonable bounds
            new_score = max(0.01, new_score)
            
            updates.append({
                'conv_id': conv.id,
                'score': new_score
            })
        
        logging.info(f"Finished score calculation")
        
        # Perform bulk update in a single transaction
        if updates:
            stmt = cls.__table__.update().\
                where(cls.__table__.c.id == db.bindparam('conv_id')).\
                values(score=db.bindparam('score'))
            
            db.session.execute(stmt, updates)
            db.session.commit()

    def to_dict(self, include_messages=True):
        data = {
            'id': self.id,
            'user_id': self.user_id,
            'start_date': self.start_date,
            'last_update': self.last_update,
            'score': self.score
        }
        if include_messages:
            data['messages'] = [message.to_dict() for message in self.messages]
        return data

    @property
    def cursor_value(self):
        """Generate a cursor value for this conversation"""
        return {
            'score': float(self.score) if self.score else 0,
            'id': self.id,
            'last_update': self.last_update.isoformat()
        }    

def encode_cursor(cursor_dict):
    """Encode cursor dictionary to base64 string"""
    return b64encode(json.dumps(cursor_dict).encode()).decode()

def decode_cursor(cursor_str):
    """Decode base64 cursor string to dictionary"""
    try:
        return json.loads(b64decode(cursor_str).decode())
    except:
        return None

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
        conversation = Conversation(
            user_id=user_id, 
            content_id=content_id
        )
        conversation.update_score(randomness_factor=0.2)

        db.session.add(conversation)
        db.session.flush()  # Flush to get the conversation ID
        db.session.commit()

        # Nudge gnosis-influencer to update the conversation
        influencer_response = requests.post(
            f"{INFLUENCER_API_URL}/api/message/ai",
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

@app.route('/api/convos/batch', methods=['POST'])
def create_batch_convos():
    if not request.json or 'user_id' not in request.json:
        logging.warning("user_id is required")
        return jsonify({"error": "user_id is required"}), 400

    user_id = request.json['user_id']
    num_convos = request.json.get('num_convos', 10)  # Default to 10 if not specified

    try:
        # Fetch all content_ids associated with the user
        content_ids = requests.get(f"{CONTENT_PROCESSOR_API_URL}/api/content_ids?user_id={user_id}").json()
        # logging.info(f"Content IDs: {content_ids}")
        if not content_ids:
            logging.warning(f"No content found for user_id: {user_id}")
            return jsonify({"error": "No content found for user"}), 404

        # Get content chunks for each content_id
        content_chunks = []
        for content_id in content_ids:
            chunks_response = requests.get(f"{CONTENT_PROCESSOR_API_URL}/api/content/{content_id}/chunks")
            # logging.info(f"Chunks response: {chunks_response.json()}")
            if chunks_response.status_code == 200:
                # Access the 'chunks' key from the response
                chunks = chunks_response.json().get('chunks', [])
                content_chunks.extend([{
                    'content_id': content_id,
                    'chunk_id': chunk['id']
                } for chunk in chunks])

        if not content_chunks:
            logging.warning(f"No content chunks found for available content")
            return jsonify({"error": "No content chunks found"}), 404

        # Filter chunks that don't already have a conversation
        available_chunks = [
            chunk for chunk in content_chunks 
            if not Message.query.filter_by(content_chunk_id=chunk['chunk_id']).first()
        ]
        # logging.info(f"Available chunks: {available_chunks}")

        if not available_chunks:
            logging.warning(f"No available chunks found for user_id: {user_id}")
            return jsonify({"error": "No available chunks found for user"}), 404

        # Select a random set of content chunks
        selected_chunks = random.sample(available_chunks, min(num_convos, len(available_chunks)))
        logging.info(f"Selected chunks: {selected_chunks}")
        # Create subprocesses to make HTTP requests to itself
        for chunk in selected_chunks:
            subprocess.Popen([
                'python', '-c',
                f"import requests; "
                f"requests.post('{CONVERSATION_API_URL}/api/convos', "
                f"json={{"
                f"'user_id': {user_id}, "
                f"'content_id': {chunk['content_id']}, "
                f"'content_chunk_id': {chunk['chunk_id']}"
                f"}})"
            ])

        logging.info(f"Batch conversation creation initiated for user_id: {user_id}")
        return jsonify({"message": "Request received"}), 202

    except Exception as e:
        logging.error(f"Error creating batch conversations: {e}")
        return jsonify({"error": "Failed to create batch conversations"}), 500

@app.route('/api/convos', methods=['GET'])
def get_convos():
    user_id = request.args.get('user_id')
    limit = request.args.get('limit', 20, type=int)
    cursor = request.args.get('cursor')
    refresh = request.args.get('refresh', 'false').lower() == 'true'

    if not user_id:
        logging.warning("user_id is required")
        return jsonify({"error": "user_id is required"}), 400

    try:
        # Base query
        query = Conversation.query.filter_by(user_id=user_id)

        # Apply cursor-based pagination
        if cursor:
            cursor_data = decode_cursor(cursor)
            if cursor_data:
                # Get conversations with lower or equal score, but for equal scores
                # use ID to ensure consistent ordering
                query = query.filter(
                    (Conversation.score < cursor_data['score']) |
                    ((Conversation.score == cursor_data['score']) & 
                     (Conversation.id < cursor_data['id']))
                )

        # Order by score (descending) and ID (descending) for consistent pagination
        conversations = query.order_by(
            Conversation.score.desc(),
            Conversation.id.desc()
        ).limit(limit + 1).all()  # Get one extra to check if there's more

        # Check if there are more results
        has_next = len(conversations) > limit
        conversations = conversations[:limit]  # Remove the extra item

        # Fetch AI profiles for each conversation
        # Create a mapping to cache AI profiles by content_id
        ai_profile_cache = {}
        conversation_data = []
        
        for conv in conversations:
            # Check if we already have the AI profile for this content_id
            if conv.content_id not in ai_profile_cache:
                # Only fetch if not in cache
                ai_response = requests.get(f"{PROFILES_API_URL}/api/ais/content/{conv.content_id}")
                ai_profile = {}
                if ai_response.status_code == 200:
                    ai_data = ai_response.json()
                    ai_profile = {
                        'display_name': ai_data.get('display_name'),
                        'name': ai_data.get('name')
                    }
                ai_profile_cache[conv.content_id] = ai_profile
            
            # Use cached profile
            conv_dict = conv.to_dict()
            conv_dict['ai_profile'] = ai_profile_cache[conv.content_id]
            conversation_data.append(conv_dict)

        # Generate next cursor
        next_cursor = None
        if has_next and conversations:
            next_cursor = encode_cursor(conversations[-1].cursor_value)

        # If refresh is requested and this is the first page
        if refresh and not cursor:
            requests.post(
                f"{CONVERSATION_API_URL}/api/convos/batch", 
                json={'user_id': user_id, 'num_convos': 5}
            )

        response_data = {
            "conversations": conversation_data,
            "next_cursor": next_cursor,
            "has_next": has_next
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
        conversation.update_score(randomness_factor=0.05)
        db.session.commit()

        # Nudge the influencer api with the conversation_id to get a reply
        influencer_response = requests.post(
            f"{INFLUENCER_API_URL}/api/message/ai",
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

# Add new shuffle endpoint
@app.route('/api/convos/shuffle', methods=['POST'])
def shuffle_conversations():
    if not request.json or 'user_id' not in request.json:
        return jsonify({"error": "user_id is required"}), 400

    user_id = request.json['user_id']
    volatility = request.json.get('volatility', 0.5)

    # Start background process
    subprocess.Popen([
        'python', '-c',
        f"import requests; "
        f"requests.post('{CONVERSATION_API_URL}/api/convos/shuffle-helper', "
        f"json={{'user_id': {user_id}, 'volatility': {volatility}}})"
    ])

    return jsonify({"message": "Shuffle initiated"}), 202  # 202 Accepted indicates the request is being processed

@app.route('/api/convos/shuffle-helper', methods=['POST'])
def shuffle_helper():
    """Helper endpoint that actually performs the shuffle"""
    if not request.json or 'user_id' not in request.json:
        return jsonify({"error": "user_id is required"}), 400

    user_id = request.json['user_id']
    volatility = request.json.get('volatility', 0.5)

    try:
        Conversation.shuffle_scores(user_id, volatility)
        return jsonify({"message": "Conversations shuffled successfully"}), 200
    except Exception as e:
        logging.error(f"Error shuffling conversations: {e}")
        return jsonify({"error": "Failed to shuffle conversations"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=C_PORT)