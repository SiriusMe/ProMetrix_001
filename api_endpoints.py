import requests
from typing import Dict, List, Optional, Union, Tuple
from dataclasses import dataclass
import os
from dotenv import load_dotenv


# Get the directory containing the script
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')

# Load environment variables from .env file
print(f"Looking for .env file at: {env_path}")
if not os.path.exists(env_path):
    raise FileNotFoundError(f".env file not found at {env_path}")

load_dotenv(env_path)

# Get and validate API base URL
api_base_url = os.getenv('API_BASE_URL')
if not api_base_url or api_base_url == 'API_BASE_URL':
    raise ValueError("Invalid API_BASE_URL in .env file. Should be like: http://172.18.7.93:9999/api/v1")

if not api_base_url.startswith(('http://', 'https://')):
    raise ValueError("API_BASE_URL must start with http:// or https://")

print(f"Loaded API_BASE_URL: {api_base_url}")

@dataclass
class APIEndpoints:
    BASE_URL: str = api_base_url
    
    # Auth endpoints
    AUTH_LOGIN = "/auth/login"
    AUTH_USER_ROLE = "/auth/users/{username}/role"
    
    # Planning endpoints
    PLANNING_ALL_ORDERS = "/planning/all_orders"
    PLANNING_GET_ORDER = "/planning/order/{order_id}"
    PLANNING_SEARCH_ORDER = "/planning/search_order"
    
    # Document endpoints
    DOCUMENTS_BY_ORDER = "/documents/by-part-number/"
    DOCUMENT_DOWNLOAD = "/documents/download-by-part-number"
    DOCUMENT_VERSION_DOWNLOAD = "/documents/{doc_id}/download/{version_id}"
    BALLOONED_DRAWING_UPLOAD = "/document-management/ballooned-drawing/upload/"
    
    # Quality endpoints
    QUALITY_CHECK = "/quality/check"
    QUALITY_MASTER_BOC = "/quality/master-boc/"
    QUALITY_MEASUREMENT_INSTRUMENTS = "/quality/master-boc/measurement-instruments"
    
    # Other endpoints
    MEASUREMENT_DATA = "/measurement/data"
    
    # Drawing endpoints
    IPID_DRAWING = "/document-management/documents/download-latest_new/{production_order}/IPID"
    ENGINEERING_DRAWING = "/document-management/documents/download-latest_new/{part_number}/ENGINEERING_DRAWING"

    # Inventory endpoints
    INVENTORY_CATEGORIES = "/api/inventory/categories/"
    INVENTORY_SUBCATEGORIES = "/api/inventory/subcategories/"
    INVENTORY_ITEMS = "/api/inventory/items/"
    INVENTORY_CALIBRATIONS = "/api/inventory/calibrations/"

    # Report endpoints
    REPORT_UPLOAD = "/document-management/report/upload/"
    REPORT_STRUCTURE = "/document-management/report/structure/"
    REPORT_FOLDER_CREATE = "/document-management/report/folder"

class APIHandler:
    def __init__(self, base_url: str = APIEndpoints.BASE_URL):
        self.base_url = base_url
        self.token = None
        self.username = None
        self.operator_id = None
        
    def check_health(self) -> bool:
        """Check if the API server is responding"""
        try:
            # Try the root endpoint instead of /health
            response = requests.get(f"{self.base_url}", timeout=5)
            print(f"Health check response: {response.status_code}")  # Debug print
            # Accept any 2xx status code as success
            return 200 <= response.status_code < 300
        except requests.RequestException as e:
            print(f"Health check failed: {str(e)}")  # Debug print
            return False

    def login(self, username: str, password: str) -> bool:
        """Login user and get authentication token"""
        try:
            # Skip health check as it might not have a dedicated health endpoint
            # Create form data
            login_data = {
                "username": username,
                "password": password
            }
            
            # Debug print
            print(f"Attempting login to: {self.base_url}{APIEndpoints.AUTH_LOGIN}")
            
            response = requests.post(
                f"{self.base_url}{APIEndpoints.AUTH_LOGIN}",
                data=login_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json"
                },
                timeout=10
            )
            
            # Debug print
            print(f"Login response status: {response.status_code}")
            # print(f"Login response content: {response.text}")
            
            response.raise_for_status()
            data = response.json()
            
            # Check if token is in the response data
            self.token = data.get("token") or data.get("access_token")
            if self.token:
                self.username = username  # Store username
                self._fetch_operator_id()  # Fetch operator ID after successful login
                
                # Get user role after successful login
                role = self.get_user_role(username)
                if role:
                    self.user_role = role  # Store user role
                
                print("Login successful")
                return True
            
            print(f"Login failed: No token in response - {data}")
            return False
            
        except requests.RequestException as e:
            print(f"Login failed: {str(e)}")
            if hasattr(e, 'response') and hasattr(e.response, 'json'):
                try:
                    error_data = e.response.json()
                    print(f"Error details: {error_data}")
                except:
                    pass
            return False
            
    def _make_request(self, endpoint, stream=False, params=None, method="GET", data=None):
        """Make a request to the API"""
        try:
            url = f"{self.base_url}{endpoint}"
            print(f"Making {method} request to: {url}")
            
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            if stream:
                # For file downloads
                response = requests.get(url, headers=headers, stream=True)
                print(f"Response status: {response.status_code}")
                
                if response.status_code == 200:
                    return response.content  # Return binary content
                else:
                    print(f"Error response: {response.text}")
                    return None
            else:
                # For regular JSON responses
                if method.upper() == "GET":
                    response = requests.get(url, headers=headers, params=params)
                elif method.upper() == "POST":
                    response = requests.post(url, headers=headers, json=data)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                    
                print(f"Response status: {response.status_code}")
                
                if response.status_code in [200, 201]:
                    return response.json()
                else:
                    print(f"Error response: {response.text}")
                    return None
                
        except Exception as e:
            print(f"Request error: {e}")
            return None
            
    def get_all_orders(self) -> List[Dict]:
        """
        Get all production orders
        
        Returns:
            List of orders with part numbers and production order numbers
        """
        response = self._make_request(APIEndpoints.PLANNING_ALL_ORDERS)
        if response:
            return response
        return []
        
    def get_order_details(self, part_number: str) -> Dict:
        """Get order details for a part number"""
        try:
            endpoint = f"/planning/search_order?part_number={part_number}"
            response = self._make_request(endpoint)
            
            if response and response.get("orders"):
                return response["orders"][0]
            return {}
            
        except Exception as e:
            print(f"Error getting order details: {str(e)}")
            return {}
        
    def submit_quality_check(self, data: Dict) -> Optional[Dict]:
        """Submit quality check data"""
        return self._make_request(
            APIEndpoints.QUALITY_CHECK,
            method="POST",
            data=data
        )

    def get_document_versions(self, production_order: str) -> Optional[List[Dict]]:
        """
        Get document versions for a production order
        """
        try:
            params = {
                'part_number': production_order,
                'doc_type_id': 17
            }
            
            response = self._make_request(APIEndpoints.DOCUMENTS_BY_ORDER, params=params)
            
            # Print response for debugging
            print(f"Document versions response: {response}")
            
            # Extract versions from the response structure
            if isinstance(response, dict):
                documents = response.get('documents', [])
                if documents and len(documents) > 0:
                    # Get the first document's ID and its versions
                    document = documents[0]
                    doc_id = document.get('id')
                    versions = document.get('versions', [])
                    
                    # Add document ID to each version
                    for version in versions:
                        version['document_id'] = doc_id
                    
                    return versions
            
            return []
            
        except Exception as e:
            print(f"Error getting document versions: {str(e)}")
            return []

    def download_latest_document(self, production_order: str, save_path: str) -> bool:
        """
        Download the latest version of a document
        
        Args:
            production_order: Production order number
            save_path: Path where to save the downloaded PDF
            
        Returns:
            bool: True if download successful, False otherwise
        """
        try:
            params = {
                'part_number': production_order,
                'doc_type_id': 17
            }
            
            url = f"{self.base_url}{APIEndpoints.DOCUMENT_DOWNLOAD}"
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/pdf"
            }
            
            print(f"Downloading document from: {url}")
            # print(f"Headers: {headers}")
            
            response = requests.get(
                url,
                params=params,
                headers=headers,
                stream=True  # Stream the response for large files
            )
            response.raise_for_status()
            
            # Save the file
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            return True
            
        except Exception as e:
            print(f"Error downloading document: {str(e)}")
            return False

    def download_specific_version(self, doc_id: int, version_id: int, save_path: str) -> bool:
        """
        Download a specific version of a document
        
        Args:
            doc_id: Document ID
            version_id: Version ID
            save_path: Path where to save the downloaded PDF
            
        Returns:
            bool: True if download successful, False otherwise
        """
        try:
            endpoint = APIEndpoints.DOCUMENT_VERSION_DOWNLOAD.format(
                doc_id=doc_id,
                version_id=version_id
            )
            
            url = f"{self.base_url}{endpoint}"
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/pdf"
            }
            
            print(f"Downloading specific version from: {url}")
            
            response = requests.get(
                url,
                headers=headers,
                stream=True
            )
            response.raise_for_status()
            
            # Save the file
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            return True
            
        except Exception as e:
            print(f"Error downloading specific version: {str(e)}")
            return False

    def get_operations(self, part_number: str) -> List[Dict]:
        """Get operations for a part number"""
        try:
            # Build the URL with query parameters
            endpoint = f"/planning/search_order?part_number={part_number}"
            response = self._make_request(endpoint)
            
            if response and response.get("orders"):
                if response["orders"][0].get("operations"):
                    return sorted(
                        response["orders"][0]["operations"],
                        key=lambda x: x["operation_number"]
                    )
            return []
            
        except Exception as e:
            print(f"Error getting operations: {str(e)}")
            return []

    def get_ipid_drawing(self, production_order: str, operation_number: str) -> Optional[bytes]:
        """
        Get IPID drawing using the new endpoint
        """
        try:
            print(f"\nAPI get_ipid_drawing called with:")
            print(f"Production Order: {production_order}")
            print(f"Operation Number: {operation_number}")
            
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Accept': 'application/pdf'
            }
            
            url = f"{self.base_url}{APIEndpoints.IPID_DRAWING.format(production_order=production_order)}"
            params = {
                'operation_number': operation_number
            }
            
            print(f"Making request to: {url}")
            print(f"With params: {params}")
            
            response = requests.get(url, headers=headers, params=params)
            
            print(f"Response status code: {response.status_code}")
            if response.status_code != 200:
                print(f"Response text: {response.text}")
            
            if response.status_code == 200:
                return response.content
            
            print(f"Failed to get IPID drawing: {response.text}")
            return None
            
        except Exception as e:
            print(f"Error getting IPID drawing: {str(e)}")
            return None

    def check_token_valid(self) -> bool:
        """Check if current token is valid"""
        if not self.token:
            return False
            
        try:
            # Try to make a simple authenticated request
            response = self._make_request(APIEndpoints.PLANNING_ALL_ORDERS)
            return response is not None
        except:
            return False

    def _fetch_operator_id(self) -> None:
        """Fetch operator ID from user role endpoint"""
        if not self.username:
            return

        try:
            endpoint = APIEndpoints.AUTH_USER_ROLE.format(username=self.username)
            response = self._make_request(endpoint)
            
            if response and isinstance(response, dict):
                self.operator_id = response.get('id')
                print(f"Operator ID set to: {self.operator_id}")
            
        except Exception as e:
            print(f"Error fetching operator ID: {str(e)}")

    def get_operator_id(self) -> Optional[int]:
        """Get the operator ID for the logged-in user"""
        return self.operator_id

    def get_user_role(self, username: str) -> Optional[str]:
        """Get user role from the API"""
        try:
            endpoint = APIEndpoints.AUTH_USER_ROLE.format(username=username)
            response = self._make_request(endpoint)
            
            if response and isinstance(response, dict):
                role = response.get('role_name', '').lower()
                print(f"User role: {role}")
                return role
            
            return None
            
        except Exception as e:
            print(f"Error fetching user role: {str(e)}")
            return None

    def get_inventory_categories(self) -> Optional[List[Dict]]:
        """Get inventory categories from the API"""
        try:
            response = self._make_request(APIEndpoints.INVENTORY_CATEGORIES)
            if response and isinstance(response, list):
                return response
            return None
        except Exception as e:
            print(f"Error fetching inventory categories: {str(e)}")
            return None

    def get_inventory_subcategories(self, category_id: int) -> Optional[List[Dict]]:
        """Get inventory subcategories for a specific category"""
        try:
            response = self._make_request(f"{APIEndpoints.INVENTORY_SUBCATEGORIES}?category_id={category_id}")
            if response and isinstance(response, list):
                return response
            return None
        except Exception as e:
            print(f"Error fetching inventory subcategories: {str(e)}")
            return None

    def get_inventory_items(self, subcategory_id: int) -> Optional[List[Dict]]:
        """Get inventory items for a specific subcategory"""
        try:
            response = self._make_request(f"{APIEndpoints.INVENTORY_ITEMS}?subcategory_id={subcategory_id}")
            if response and isinstance(response, list):
                return response
            return None
        except Exception as e:
            print(f"Error fetching inventory items: {str(e)}")
            return None

    def logout(self) -> bool:
        """Clear authentication token and user data"""
        try:
            # Clear authentication data
            self.token = None
            self.user_role = None
            self.username = None
            self.operator_id = None
            
            return True
        except Exception as e:
            print(f"Error during logout: {str(e)}")
            return False

    def create_master_boc(self, payload: dict) -> Optional[dict]:
        """Create master BOC entry"""
        try:
            response = requests.post(
                f"{self.base_url}{APIEndpoints.QUALITY_MASTER_BOC}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json"
                }
            )
            
            print(f"Master BOC Response: {response.status_code}")
            print(f"Response content: {response.text}")
            
            if response.status_code in [200, 201]:
                return response.json()
            
            print(f"Failed to create master BOC: {response.text}")
            return None
            
        except Exception as e:
            print(f"Error creating master BOC: {str(e)}")
            return None

    def create_stage_inspection(self, payload: dict) -> Optional[dict]:
        """Create stage inspection entry"""
        try:
            response = requests.post(
                f"{self.base_url}/quality/stage-inspection/",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json"
                }
            )
            
            print(f"Stage Inspection Response: {response.status_code}")
            print(f"Response content: {response.text}")
            
            if response.status_code in [200, 201]:
                return response.json()
            
            print(f"Failed to create stage inspection: {response.text}")
            return None
            
        except Exception as e:
            print(f"Error creating stage inspection: {str(e)}")
            return None

    def get_calibrations(self) -> Optional[List[Dict]]:
        """Get all calibration data with fresh data every time"""
        try:
            # Add no-cache headers to force fresh data
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
            
            # Make request with custom headers
            response = requests.get(
                f"{self.base_url}{APIEndpoints.INVENTORY_CALIBRATIONS}",
                headers=headers,
                timeout=30  # Increased timeout for larger data sets
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching calibrations: Status {response.status_code}")
                print(f"Response: {response.text}")
                return None
                
        except Exception as e:
            print(f"Error fetching calibrations: {str(e)}")
            return None

    def upload_ballooned_drawing(self, production_order: str, ipid: str, file_path: str) -> bool:
        """Upload ballooned drawing to Minio"""
        try:
            url = f"{self.base_url}{APIEndpoints.BALLOONED_DRAWING_UPLOAD}"
            
            # Extract operation number from IPID (format: IPID-partnumber-opno)
            operation_number = ipid.split('-')[-1] if ipid and '-' in ipid else None
            if not operation_number:
                raise ValueError("Could not extract operation number from IPID")
            
            # Prepare the files and data
            with open(file_path, 'rb') as f:
                files = {'file': f}
                data = {
                    'production_order': production_order,
                    'ipid': ipid,
                    'document_name': f"Ballooned_{production_order}_{ipid}",
                    'version_number': "1.0",
                    'description': f"Ballooned drawing for {production_order} - {ipid}",
                    'operation_number': operation_number
                }
                
                headers = {
                    "Authorization": f"Bearer {self.token}"
                }
                
                response = requests.post(url, headers=headers, data=data, files=files)
                print(f"Upload response status: {response.status_code}")
                print(f"Upload response: {response.text}")
                
                return response.status_code in [200, 201]
                
        except Exception as e:
            print(f"Error uploading ballooned drawing: {str(e)}")
            return False

    def upload_inspection_report(self, production_order: str, operation_number: str, file_path: str, folder_path: str, document_name: str, description: str = "") -> bool:
        """Upload inspection report PDF to server"""
        try:
            url = f"{self.base_url}{APIEndpoints.REPORT_UPLOAD}"
            
            # Prepare the files and data
            with open(file_path, 'rb') as f:
                files = {'file': f}
                data = {
                    'production_order': production_order,
                    'operation_number': operation_number,
                    'folder_path': folder_path,  # Use the folder name directly without REPORT/REPORT prefix
                    'document_name': document_name,
                    'description': description,
                    'version_number': "1.0",
                    'order_number': production_order,
                    'metadata': '{}'
                }
                
                headers = {
                    "Authorization": f"Bearer {self.token}"
                }
                
                response = requests.post(url, headers=headers, data=data, files=files)
                print(f"Report upload response status: {response.status_code}")
                print(f"Report upload response: {response.text}")
                
                return response.status_code in [200, 201]
                
        except Exception as e:
            print(f"Error uploading inspection report: {str(e)}")
            return False

    def get_report_structure(self):
        """Get the report folder structure"""
        try:
            return self._make_request(APIEndpoints.REPORT_STRUCTURE)
        except Exception as e:
            print(f"Error getting report structure: {str(e)}")
            return None

    def create_report_folder(self, name: str, parent_id: int = 0) -> dict:
        """Create a new folder in the report structure"""
        try:
            if not self.token:
                print("Error: No authentication token available")
                return None
                
            url = f"{self.base_url}{APIEndpoints.REPORT_FOLDER_CREATE}"
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            data = {
                "name": name,
                "parent_id": parent_id
            }
            
            print(f"Creating folder with data: {data}")
            print(f"Using URL: {url}")
            print(f"With headers: {headers}")
            
            response = requests.post(url, headers=headers, json=data)
            print(f"Create folder response: {response.status_code}")
            print(f"Response content: {response.text}")
            
            if response.status_code in [200, 201]:
                return response.json()
            elif response.status_code == 404:
                print("Error: Folder creation endpoint not found. Please check the API endpoint URL.")
            elif response.status_code == 401:
                print("Error: Unauthorized. Please check your authentication token.")
            else:
                print(f"Error: Unexpected status code {response.status_code}")
                
            return None
            
        except Exception as e:
            print(f"Error creating report folder: {str(e)}")
            return None

    def check_quantity_completion(self, order_id: int, ipid: str) -> bool:
        """Check if a quantity is completed for a given order and IPID"""
        try:
            endpoint = f"/quality/ftp/{order_id}/{ipid}"
            response = requests.get(
                f"{self.base_url}{endpoint}",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json"
                }
            )
            
            print(f"Quantity completion check response: {response.status_code}")
            print(f"Response content: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                return data.get('is_completed', False)
            
            return False
            
        except Exception as e:
            print(f"Error checking quantity completion: {str(e)}")
            return False

# Create singleton instance
api = APIHandler()