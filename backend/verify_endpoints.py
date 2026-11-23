import sys
from fastapi.testclient import TestClient
from app.main import app

def run_verifications():
    print("=" * 60)
    print("AI Chief of Staff - Backend & Groq API Verification")
    print("=" * 60)

    client = TestClient(app)

    # 1. Test /api/health
    print("\n[Step 1] Testing GET /api/health ...")
    health_res = client.get("/api/health")
    print(f"Status Code: {health_res.status_code}")
    print(f"Response: {health_res.json()}")
    assert health_res.status_code == 200, f"Expected 200, got {health_res.status_code}"
    health_data = health_res.json()
    assert health_data["status"] == "healthy"
    assert health_data["groq_configured"] is True, "GROQ_API_KEY should be configured"
    print("✓ Health check PASSED")

    # 2. Test POST /api/ai/test with default model (openai/gpt-oss-120b)
    print("\n[Step 2] Testing POST /api/ai/test with Groq model (openai/gpt-oss-120b) ...")
    test_payload = {
        "message": "Give me a 1-sentence greeting confirming you are ready as my AI Chief of Staff.",
        "system_prompt": "You are an elite, proactive AI Chief of Staff. Answer concisely."
    }
    ai_res = client.post("/api/ai/test", json=test_payload)
    print(f"Status Code: {ai_res.status_code}")
    ai_data = ai_res.json()
    print(f"Model used: {ai_data.get('model')}")
    print(f"Response Text:\n  -> {ai_data.get('response')}")
    print(f"Usage: {ai_data.get('usage')}")
    assert ai_res.status_code == 200, f"Expected 200, got {ai_res.status_code}: {ai_data}"
    assert ai_data["status"] == "success"
    assert len(ai_data["response"]) > 0, "Response content should not be empty"
    print("✓ Groq API integration test PASSED")

    # 3. Test Invalid Model Handling
    print("\n[Step 3] Testing error handling with an invalid model name ...")
    bad_payload = {
        "message": "Hello",
        "model": "non-existent-model-xyz-123"
    }
    bad_res = client.post("/api/ai/test", json=bad_payload)
    print(f"Status Code: {bad_res.status_code}")
    print(f"Detail: {bad_res.json().get('detail')}")
    assert bad_res.status_code in [500, 502], f"Expected 500 or 502, got {bad_res.status_code}"
    print("✓ Error handling test PASSED")

    print("\n" + "=" * 60)
    print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_verifications()
