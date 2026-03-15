import os
import random
import string
import json
import hmac
import hashlib
import base64
import urllib.parse
import logging
import requests
import datetime
import email.utils

class OnshapeClient:
    def __init__(self, access_key, secret_key, base_url="https://cad.onshape.com"):
        self.access_key = access_key.strip()
        self.secret_key = secret_key.strip().encode('utf-8')
        self.base_url = base_url
        self.logger = logging.getLogger("OnshapeClient")

    def _generate_nonce(self):
        chars = string.ascii_letters + string.digits
        return "".join(random.choice(chars) for _ in range(25))

    def _make_headers(self, method, path, query={}, content_type="application/json", accept="application/vnd.onshape.v1+json"):
        # Onshape API specific: Content-Type should be empty for GET and DELETE
        if method.upper() in ['GET', 'DELETE']:
            content_type = ""
        
        date = email.utils.formatdate(usegmt=True)
        nonce = self._generate_nonce()
        
        # Build query string for signature using urlencode to match reference
        if query:
            query_string = urllib.parse.urlencode(query)
        else:
            query_string = ""
        
        # Signature String Construction
        # Method\nNonce\nDate\nContent-Type\nPath\nQuery\n (note trailing newline)
        # Reference implementation lowercases the WHOLE string AFTER construction
        s = (
            f"{method}\n"
            f"{nonce}\n"
            f"{date}\n"
            f"{content_type}\n"
            f"{path}\n"
            f"{query_string}\n"
        ).lower()

        hmac_obj = hmac.new(self.secret_key, s.encode('utf-8'), digestmod=hashlib.sha256)
        signature = base64.b64encode(hmac_obj.digest()).decode('utf-8')

        headers = {
            "On-Nonce": nonce,
            "Date": date,
            "Authorization": f"On {self.access_key}:HmacSHA256:{signature}",
            "Accept": accept,
            "User-Agent": "Onshape Python Sample App"
        }
        
        if content_type:
            headers["Content-Type"] = content_type
            
        return headers

    def _request(self, method, endpoint, params=None, data=None, base_url=None):
        path = endpoint if endpoint.startswith("/api") else f"/api{endpoint}"
        current_base_url = base_url or self.base_url
        url = f"{current_base_url}{path}"
        
        # Ensure params is a dict
        params = params or {}
        
        headers = self._make_headers(method, path, query=params)
        
        try:
            response = requests.request(method, url, headers=headers, params=params, json=data, allow_redirects=False)
            
            # Handle 307 Redirect
            if response.status_code == 307:
                location = urllib.parse.urlparse(response.headers["Location"])
                new_base_url = f"{location.scheme}://{location.netloc}"
                new_path = location.path
                new_params = urllib.parse.parse_qs(location.query)
                # parse_qs returns lists, we need single values
                new_params = {k: v[0] for k, v in new_params.items()}
                
                self.logger.info(f"Redirecting to {new_base_url}{new_path}")
                return self._request(method, new_path, params=new_params, data=data, base_url=new_base_url)

            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"HTTP Error: {e.response.status_code} {e.response.text}")
            raise

    def get_documents(self):
        """Get list of documents sorted by last modified date."""
        params = {
            'ownerType': '1',
            'sortColumn': 'modifiedAt',
            'sortOrder': 'desc',
            'offset': '0',
            'limit': '20'
        }
        return self._request("GET", "/documents", params=params)
    
    def get_document_workspaces(self, did):
        return self._request("GET", f"/documents/{did}/workspaces")

    def get_elements(self, did, wid):
        return self._request("GET", f"/documents/d/{did}/w/{wid}/elements")

    def get_document_thumbnail(self, did, size="300x300"):
        """
        Get thumbnail for a document.
        size: thumbnail size, e.g., "70x40", "300x170", "300x300", "600x340"
        Returns: image bytes or None
        """
        endpoint = f"/thumbnails/d/{did}/w/w/s/{size}"
        path = f"/api{endpoint}"
        url = f"{self.base_url}{path}"
        headers = self._make_headers("GET", path, query={})
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response.content
        except Exception as e:
            self.logger.warning(f"Failed to fetch document thumbnail: {e}")
        return None

    def get_thumbnail(self, path):
        """
        Fetch thumbnail image data from a given API path or full URL.
        path: Path starting with /thumbnails/... or full Onshape API URL
        Returns: image bytes or None
        """
        # Parse the input path
        parsed = urllib.parse.urlparse(path)
        
        # Extract the endpoint path (e.g., /api/thumbnails/...)
        endpoint_path = parsed.path
        if not endpoint_path.startswith("/api"):
            endpoint_path = f"/api{endpoint_path}"
        
        # Extract query parameters
        params = urllib.parse.parse_qs(parsed.query)
        params = {k: v[0] for k, v in params.items()}
        
        # Generate headers for the specific endpoint path and params
        # Use image/* accept header for thumbnails to avoid 406
        headers = self._make_headers("GET", endpoint_path, query=params, accept="image/*")
        url = f"{self.base_url}{endpoint_path}"
        
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return response.content
            else:
                self.logger.warning(f"Failed to fetch thumbnail: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            self.logger.warning(f"Exception fetching thumbnail: {e}")
        return None

    def export_element_as_3mf(self, did, wid, eid, element_type, output_path):
        """
        Exports a Part Studio or Assembly as 3MF.
        element_type: "PARTSTUDIO" or "ASSEMBLY"
        """
        endpoint_type = "partstudios" if element_type == "PARTSTUDIO" else "assemblies"
        endpoint = f"/{endpoint_type}/d/{did}/w/{wid}/e/{eid}/translations"
        
        # Part Studios require additional parameters for 3MF export
        if element_type == "PARTSTUDIO":
            payload = {
                "formatName": "3MF",
                "storeInDocument": False,
                "resolution": "fine",  # Options: coarse, medium, fine
                "units": "millimeter"  # Common for 3D printing
            }
        else:  # ASSEMBLY
            payload = {
                "formatName": "3MF",
                "storeInDocument": False
            }
        
        # 1. Start Translation
        try:
            initial_response = self._request("POST", endpoint, data=payload)
            translation_id = initial_response.get("id")
            if not translation_id:
                raise Exception(f"Failed to start translation: {initial_response}")
        except Exception as e:
            self.logger.error(f"Translation start failed: {e}")
            raise

        # 2. Poll for completion
        import time
        max_retries = 60  # Increased timeout for larger files
        for i in range(max_retries):
            status_res = self._request("GET", f"/translations/{translation_id}")
            state = status_res.get("requestState")
            
            self.logger.info(f"Translation status: {state} (attempt {i+1}/{max_retries})")
            
            if state == "DONE":
                # Get the download URL
                download_url = status_res.get("resultExternalDataIds")
                if download_url and isinstance(download_url, list) and len(download_url) > 0:
                    # Use the first external data ID to construct download URL
                    external_id = download_url[0]
                    download_endpoint = f"/documents/d/{did}/externaldata/{external_id}"
                    
                    # Download using authenticated request
                    path = f"/api{download_endpoint}"
                    url = f"{self.base_url}{path}"
                    headers = self._make_headers("GET", path, query={})
                    
                    file_res = requests.get(url, headers=headers, stream=True)
                    file_res.raise_for_status()
                    
                    with open(output_path, 'wb') as f:
                        for chunk in file_res.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    self.logger.info(f"Successfully downloaded to {output_path}")
                    return True
                else:
                    raise Exception("No download URL found in translation result")
                
            elif state == "FAILED":
                failure_reason = status_res.get('failureReason', 'Unknown error')
                raise Exception(f"Translation failed: {failure_reason}")
            
            time.sleep(3)  # Increased polling interval
            
        raise Exception("Translation timed out")