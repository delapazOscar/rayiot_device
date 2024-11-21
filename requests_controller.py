import requests

class RequestsController:
    def __init__(self, endpoint, access_token, account_id):
        self.endpoint = endpoint
        self.access_token = access_token
        self.account_id = account_id

    def make_request(self, method=None, payload=None, res_id=False, res_model=None):
        data = {
            "params": {
                "res_model": res_model,
                "access_token": self.access_token,
                "account_id": self.account_id,
                "res_method": method,
                "res_params": payload,
            }
        }

        if res_id:
            data["params"]["res_id"] = res_id

        headers = {
            'Content-Type': 'application/json'
        }

        print("Request Data:", data)
        print(f"Endpoint {self.endpoint}")

        try:
            # Use the passed method for the HTTP request
            response = requests.post(self.endpoint, json= data, timeout=60)
            return response
            print("Response Status Code:", response.status_code)
            print("Response Content:", response.json())
        except requests.exceptions.ConnectionError:
            print("Failed to connect to the endpoint. Please check the network connection.")
        except requests.exceptions.Timeout:
            print("The request timed out.")
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
