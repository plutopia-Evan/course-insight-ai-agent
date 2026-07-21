import requests


BASE_URL = "http://127.0.0.1:8000"



def test_root():

    response = requests.get(
        f"{BASE_URL}/"
    )

    assert response.status_code == 200



def test_analysis_api():

    response = requests.post(
        f"{BASE_URL}/analysis",
        json={}
    )

    assert response.status_code in [
        200,
        422
    ]



def test_feedback_api():

    response = requests.post(
        f"{BASE_URL}/feedback_analysis",
        json={}
    )

    assert response.status_code in [
        200,
        422
    ]



def test_report_api():

    response = requests.post(
        f"{BASE_URL}/generate_report",
    )

    assert response.status_code in [
        200,
        422,
        405
    ]