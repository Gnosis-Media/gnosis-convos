import requests
import json
import time

# Base URL for the local instance
BASE_URL = 'http://localhost:5000'

def print_response(response):
    print(f"Status Code: {response.status_code}")
    print("Response:")
    print(json.dumps(response.json(), indent=2))
    print("\n" + "="*50 + "\n")

def test_create_conversation():
    print("Testing POST /api/convos - Create new conversation")
    data = {
        "user_id": 1,
        "content_id": 1,
        "content_chunk_id": 1
    }
    response = requests.post(f"{BASE_URL}/api/convos", json=data)
    print_response(response)
    return response.json().get('conversation_id') if response.status_code == 201 else None

def test_create_batch_conversations():
    print("Testing POST /api/convos/batch - Create batch of conversations")
    data = {
        "user_id": 1,
        "num_convos": 5
    }
    response = requests.post(f"{BASE_URL}/api/convos/batch", json=data)
    print_response(response)

def test_get_conversations():
    print("Testing GET /api/convos - Get conversations (ordered)")
    params = {
        "user_id": 1,
        "limit": 5,
        "random": "false"
    }
    response = requests.get(f"{BASE_URL}/api/convos", params=params)
    print_response(response)

def test_get_random_conversations():
    print("Testing GET /api/convos - Get random conversations")
    params = {
        "user_id": 1,
        "limit": 5,
        "random": "true"
    }
    response = requests.get(f"{BASE_URL}/api/convos", params=params)
    print_response(response)

def test_add_reply(conversation_id):
    print(f"Testing PUT /api/convos/{conversation_id}/reply - Add reply")
    data = {
        "message": "This is a test reply from the user"
    }
    response = requests.put(f"{BASE_URL}/api/convos/{conversation_id}/reply", json=data)
    print_response(response)

def test_delete_conversation(conversation_id):
    print(f"Testing DELETE /api/convos/{conversation_id} - Delete conversation")
    response = requests.delete(f"{BASE_URL}/api/convos/{conversation_id}")
    print_response(response)

def test_get_conversations_with_pagination():
    print("Testing GET /api/convos - Get conversations with pagination")
    
    # First page
    params = {
        "user_id": 4,
        "limit": 2  # Small limit to test pagination
    }
    response = requests.get(f"{BASE_URL}/api/convos", params=params)
    print("First page:")
    print_response(response)
    
    # Get all pages
    all_conversations = []
    next_cursor = response.json().get('next_cursor')
    page_count = 1
    
    while next_cursor and page_count < 5:  # Limit to 5 pages for testing
        params['cursor'] = next_cursor
        response = requests.get(f"{BASE_URL}/api/convos", params=params)
        print(f"Page {page_count + 1}:")
        print_response(response)
        
        all_conversations.extend(response.json().get('conversations', []))
        next_cursor = response.json().get('next_cursor')
        page_count += 1
    
    print(f"Total conversations fetched: {len(all_conversations)}")
    
    # Verify ordering
    scores = [conv.get('score', 0) for conv in all_conversations]
    assert all(scores[i] >= scores[i+1] for i in range(len(scores)-1)), "Scores are not in descending order"
    print("✓ Scores are properly ordered")

def test_refresh_conversations():
    print("Testing GET /api/convos with refresh parameter")
    params = {
        "user_id": 1,
        "limit": 5,
        "refresh": "true"
    }
    response = requests.get(f"{BASE_URL}/api/convos", params=params)
    print_response(response)

def test_shuffle_scores():
    print("Testing POST /api/convos/shuffle - Shuffle scores")
    data = {
        "user_id": 4,
        "volatility": 0.9
    }
    response = requests.post(f"{BASE_URL}/api/convos/shuffle", json=data)
    print_response(response)

if __name__ == "__main__":
    # Run all tests
    print("Starting API tests...\n")

    # Create a conversation and get its ID
    # conversation_id = test_create_conversation()
    
    
    # Test batch creation
    # test_create_batch_conversations()
    
    # Wait a moment for batch operations to complete
    # time.sleep(2)
    
    # time.sleep(2)

    # Test pagination
    test_get_conversations_with_pagination()

    # # Test refresh functionality
    # test_refresh_conversations()
    
    # Test reply
    # test_add_reply(458)

    # Test shuffle
    # test_shuffle_scores()
    
    # Test deletion
    # test_delete_conversation(conversation_id)        
   