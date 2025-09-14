"""Your FastAPI app now supports all the necessary operations:

GET /view → View all alumni (raw JSON dump).

POST /create_alumni → Add new alumni record + auto-generate ID.

POST /upload_photo/{alumni_id} → Upload a profile photo for an existing alumni.

GET /sort_alumni → Sort alumni list (e.g., by name, batch, etc.).

GET /alumni/{alumni_id} → Get details of a specific alumni.

DELETE /alumni/{alumni_id} → Delete alumni + their photo.

PUT /update_alumni/{alumni_id} → Update details (firstname, organization, etc.).

PUT /update-photo/{alumni_id} → Replace profile photo.

PUT /update_id/{old_id} → Update alumni’s ID (e.g., change year)."""

#
#venv\Scripts\Activate.bat
# uvicorn app:app --reload



# Importing Necessary Libraries
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Path, Body
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional, ClassVar, Dict, Annotated
import json
import re
import os
import uuid
from random import randint
from fastapi.openapi.utils import get_openapi
import shutil
from PIL import Image
import io



#FastAPI App Initialization
app = FastAPI()

#Alumni Model with Required Restrictions
class Alumni(BaseModel):
    id: str
    firstname: Annotated[str, Field(..., description="First name of the alumni")]
    surname: Annotated[Optional[str], Field(None, description="Surname of the alumni")]
    gender: Annotated[str, Field(..., description="Gender (Male, Female, Other)")]
    batch: Annotated[str, Field(..., description="Batch (Academic Year, e.g., 2008-10)")]
    linkedin_url: Annotated[str, Field(..., description="LinkedIn Profile URL")]
    current_organization: Annotated[Optional[str], Field(None, description="Current Organization")]
    current_position: Annotated[Optional[str], Field(None, description="Current Position / Title")]
    current_location: Annotated[Optional[str], Field(None, description="Current Location")]
    Industry_experiences: Annotated[Optional[float], Field(None, gt=-1, lt=50, description="Years of Experience")]
    software_skill_1: Annotated[Optional[str], Field(None, description="Software Skill 1")]
    software_skill_2: Annotated[Optional[str], Field(None, description="Software Skill 2")]
    software_skill_3: Annotated[Optional[str], Field(None, description="Software Skill 3")]
    programming_lang_1: Annotated[Optional[str], Field(None, description="Programming Language 1")]
    programming_lang_2: Annotated[Optional[str], Field(None, description="Programming Language 2")]
    programming_lang_3: Annotated[Optional[str], Field(None, description="Programming Language 3")]
    profile_photo: Annotated[Optional[str], Field(None, description="Profile photo filename")]

    @field_validator("firstname", "surname", mode="before")
    @classmethod
    def capitalize_name(cls, v: Optional[str]) -> Optional[str]:
        return v.capitalize() if v else v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        valid_genders = ["Male", "Female", "Other"]
        if v not in valid_genders:
            raise ValueError("Gender must be Male, Female, or Other")
        return v

    @field_validator("batch")
    @classmethod
    def validate_batch(cls, v: str) -> str:
        pattern = r"^(20\d{2})-(\d{2})$"  # e.g., 2008-10
        match = re.match(pattern, v)
        if not match:
            raise ValueError("Batch must be in format YYYY-YY (e.g., 2008-10)")
        start_year = int(match.group(1))
        end_year = int(match.group(2)) + (start_year // 100) * 100
        if end_year != start_year + 2:
            raise ValueError("Batch must represent consecutive years (e.g., 2008-10)")
        return v

    class Profile(BaseModel):
        linkedin_url: str

    @field_validator("linkedin_url")
    @classmethod
    def validate_linkedin_url(cls, v: str) -> str:
        pattern = r"^(https?://)?(www\.)?linkedin\.com/in/[\w-]+/?$"
        if not re.match(pattern, v):
            raise ValueError(
                "Invalid LinkedIn URL. Must be a valid LinkedIn profile URL "
                "(e.g., https://www.linkedin.com/in/username)"
            )
        return v


 # Class-level counter dictionary for batch-specific serial numbers
    _batch_counts: ClassVar[Dict[str, int]] = {}

    @classmethod
    def create(cls, batch: str, **data):
        # Increment batch-specific counter
        count = cls._batch_counts.get(batch, 0) + 1
        cls._batch_counts[batch] = count
        # Format ID: 3-digit serial number + batch (e.g., 003-2008-10)
        custom_id = f"{count:03d}-{batch}"
        return cls(id=custom_id, batch=batch, **data)



#JSON File and Utility Functions
# JSON file to store alumni data and batch counts
DATA_FILE = "alumni_data.json"
PHOTO_DIR = "photo/"
os.makedirs(PHOTO_DIR, exist_ok=True)


# Utility functions to load/save data
def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"alumni": {}, "batch_counts": {}}
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            # Load batch counts to ensure consistent IDs
            Alumni._batch_counts = {k: int(v) for k, v in data.get("batch_counts", {}).items()}
            return data
    except json.JSONDecodeError:
        return {"alumni": {}, "batch_counts": {}}

def save_data(data: dict) -> None:
    # Save batch counts alongside alumni data
    data["batch_counts"] = Alumni._batch_counts
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


@app.get("/view")
def view():
    data = load_data()
    return data


# 1️⃣ Create Alumni (JSON only)
@app.post("/create_alumni")
async def create_alumni(alumni: Alumni):
    try:
        data = load_data()

        # ✅ Exclude id and batch so classmethod can handle them
        alumni_obj = Alumni.create(batch=alumni.batch, **alumni.model_dump(exclude={"id", "batch"}))

        if alumni_obj.id in data.get("alumni", {}):
            raise HTTPException(status_code=400, detail="Alumni ID already exists")

        # Save to JSON
        data.setdefault("alumni", {})[alumni_obj.id] = alumni_obj.model_dump()
        save_data(data)

        return {"message": "Alumni created successfully", "id": alumni_obj.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





# 2️⃣ Upload photo for an existing alumni
# 2️⃣ Upload photo for an existing alumni (with overwrite protection)
@app.post("/upload_photo/{alumni_id}")
async def upload_photo(alumni_id: str, profile_photo: UploadFile = File(...)):
    data = load_data()

    if alumni_id not in data.get("alumni", {}):
        raise HTTPException(status_code=404, detail="Alumni not found")

    # Always save as JPG
    photo_filename = f"{alumni_id}.jpg"
    photo_path = os.path.join(PHOTO_DIR, photo_filename)

    try:
        contents = await profile_photo.read()
        with open(photo_path, "wb") as buffer:
            buffer.write(contents)

        # Update JSON record
        data["alumni"][alumni_id]["profile_photo"] = photo_filename
        save_data(data)

        return {"message": "Photo uploaded successfully", "filename": photo_filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving photo: {str(e)}")


# for sorting
@app.get("/sort_alumni")
def sort_alumni(
    sort_by: Optional[str] = Query(None, description="Sort by 'Industry_experiences' only"),
    order: str = Query("asc", description="Sort in asc or desc order"),
    batch: Optional[str] = Query(None, description="Filter by specific batch (e.g., 2008-10)"),
    gender: Optional[str] = Query(None, description="Filter by gender (Male, Female, Other)")
):
    data = load_data().get("alumni", {})

    # Convert dict to list
    alumni_list = list(data.values())

    # 🔹 Filter by batch if provided
    if batch:
        alumni_list = [a for a in alumni_list if a.get("batch") == batch]

    # 🔹 Filter by gender if provided
    if gender:
        alumni_list = [a for a in alumni_list if a.get("gender") == gender]

    # 🔹 Sorting (only Industry_experiences supported)
    if sort_by:
        if sort_by != "Industry_experiences":
            raise HTTPException(
                status_code=400,
                detail="You can only sort by 'Industry_experiences'"
            )
        if order not in ["asc", "desc"]:
            raise HTTPException(status_code=400, detail="Order must be 'asc' or 'desc'")

        reverse_sort = True if order == "desc" else False
        alumni_list = sorted(
            alumni_list,
            key=lambda x: x.get("Industry_experiences", 0) or 0,
            reverse=reverse_sort
        )

    return {"total": len(alumni_list), "results": alumni_list}



@app.get("/alumni/{alumni_id}")
def get_alumni(
    alumni_id: str = Path(
        ..., 
        description="ID of the alumni in the database", 
        example="001-2008-10"
    )
):
    data = load_data()
    alumni_records = data.get("alumni", {})

    if alumni_id not in alumni_records:
        raise HTTPException(status_code=404, detail="Alumni not found")

    return alumni_records[alumni_id]




# 3️⃣ Update Alumni
@app.put("/update_alumni/{alumni_id}")
async def update_alumni(
    alumni_id: str,
    updated_data: Alumni
):
    try:
        data = load_data()
        alumni_records = data.get("alumni", {})

        if alumni_id not in alumni_records:
            raise HTTPException(status_code=404, detail="Alumni not found")

        # Preserve ID & batch (don’t allow change)
        updated_dict = updated_data.model_dump()
        updated_dict["id"] = alumni_id
        updated_dict["batch"] = alumni_records[alumni_id]["batch"]

        # Preserve profile photo if not updated
        if not updated_dict.get("profile_photo"):
            updated_dict["profile_photo"] = alumni_records[alumni_id].get("profile_photo")

        # Save back
        data["alumni"][alumni_id] = updated_dict
        save_data(data)

        return {"message": "Alumni updated successfully", "alumni": updated_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/alumni/{alumni_id}")
def delete_alumni(alumni_id: str):
    data = load_data()
    store = data.get("alumni", {})

    # find & remove record
    record = store.pop(alumni_id, None)
    if record is None:
        raise HTTPException(status_code=404, detail="Alumni not found")

    # delete photo if present
    photo = record.get("profile_photo")
    if photo:
        photo_path = os.path.join(PHOTO_DIR, photo)
        if os.path.isfile(photo_path):
            os.remove(photo_path)

    # save back
    data["alumni"] = store
    save_data(data)
    return {"message": f"Alumni {alumni_id} deleted successfully"}



# 🔄 Update photo (replaces old one safely)
@app.put("/update-photo/{alumni_id}")
async def update_photo(alumni_id: str, new_photo: UploadFile = File(...)):
    data = load_data()
    alumni = data.get("alumni", {}).get(alumni_id)

    if not alumni:
        raise HTTPException(status_code=404, detail="Alumni not found")

    photo_filename = f"{alumni_id}.jpg"
    photo_path = os.path.join(PHOTO_DIR, photo_filename)

    try:
        # Overwrite old file directly
        contents = await new_photo.read()
        with open(photo_path, "wb") as buffer:
            buffer.write(contents)

        alumni["profile_photo"] = photo_filename
        save_data(data)

        return {"message": "Photo updated successfully", "filename": photo_filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating photo: {str(e)}")


@app.put("/update_id/{old_id}")
def update_alumni_id(old_id: str, new_batch: str = Body(..., embed=True)):
    data = load_data()
    alumni = data.get("alumni", {})

    if old_id not in alumni:
        raise HTTPException(status_code=404, detail="Alumni not found")

    # Create new Alumni with new batch
    alumni_obj = Alumni.create(
        batch=new_batch,
        **{k: v for k, v in alumni[old_id].items() if k not in ["id", "batch"]}
    )
    new_id = alumni_obj.id

    # RENAME PHOTO FILE
    old_photo_path = os.path.join(PHOTO_DIR, f"{old_id}.jpg")
    new_photo_path = os.path.join(PHOTO_DIR, f"{new_id}.jpg")
    
    if os.path.exists(old_photo_path):
        os.rename(old_photo_path, new_photo_path)
        alumni_obj = alumni_obj.model_copy(update={"profile_photo": f"{new_id}.jpg"})

    # Update JSON
    del alumni[old_id]
    alumni[new_id] = alumni_obj.model_dump()
    save_data(data)

    return {"message": f"Alumni ID updated from {old_id} to {new_id}"}

# 👀 View photo
@app.get("/view_photo/{alumni_id}")
async def view_photo(alumni_id: str):
    data = load_data()
    alumni = data.get("alumni", {}).get(alumni_id)

    if not alumni:
        raise HTTPException(status_code=404, detail="Alumni not found")

    photo_filename = alumni.get("profile_photo") or f"{alumni_id}.jpg"
    photo_path = os.path.join(PHOTO_DIR, photo_filename)

    if not os.path.exists(photo_path):
        raise HTTPException(status_code=404, detail="Profile photo not found")

    return FileResponse(photo_path, media_type="image/jpeg", filename=photo_filename)


@app.get("/download/json")
def download_json():
    file_path = "alumni_data.json"
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="application/json", filename="alumni_data.json")
    return {"error": "File not found"}


# API to download all photos as a ZIP
@app.get("/download/photos")
def download_all_photos():
    zip_path = "all_photos.zip"

    # Create a zip file
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for root, dirs, files in os.walk(PHOTO_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, arcname=file)  # arcname keeps only file name in zip

    # Send the zip file as response
    if os.path.exists(zip_path):
        return FileResponse(zip_path, media_type="application/zip", filename="all_photos.zip")
    return {"error": "No photos found"}


import os
import zipfile
import io
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

    
