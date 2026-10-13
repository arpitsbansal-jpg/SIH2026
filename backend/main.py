import os
import re
import uuid
import hashlib
import secrets
from io import BytesIO
from pathlib import Path

import torch
import torch.nn as nn
from torchvision import models, transforms
import numpy as np

import mysql.connector
from mysql.connector import Error

from PIL import (
    Image,
    ImageStat,
    ImageFilter,
    UnidentifiedImageError,
)

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
    Request,
)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel


# =========================================================
# RETINOVA
# Frontend -> FastAPI -> MySQL + AI Model
# =========================================================

app = FastAPI(title="RETINOVA API")


# =========================================================
# SIMPLE SESSION SYSTEM
# =========================================================

sessions = {}

PORTAL_ROLES = {
    "/patient.html": "patient",
    "/doctor.html": "doctor",
    "/admin.html": "admin",
}


@app.middleware("http")
async def protect_portal_pages(request: Request, call_next):

    required_role = PORTAL_ROLES.get(
        request.url.path
    )

    if required_role:

        session_id = request.cookies.get(
            "retinova_session"
        )

        user = sessions.get(
            session_id
        )

        if not user:

            return RedirectResponse(
                "/login.html",
                status_code=303
            )

        if user["role"] != required_role:

            return RedirectResponse(
                f"/{user['role']}.html",
                status_code=303
            )

    return await call_next(request)


# =========================================================
# DATABASE CONFIGURATION
# =========================================================

MYSQL_HOST = os.getenv(
    "RETINOVA_DB_HOST",
    "localhost"
)

MYSQL_USER = os.getenv(
    "RETINOVA_DB_USER",
    "root"
)

MYSQL_PASSWORD = os.getenv(
    "RETINOVA_DB_PASSWORD",
    "MYSQLASSWORD"
)

MYSQL_DATABASE = os.getenv(
    "RETINOVA_DB_NAME",
    "retinova"
)


# =========================================================
# PROJECT PATHS
# =========================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

UPLOAD_DIR = (
    BASE_DIR / "uploads"
)

UPLOAD_DIR.mkdir(
    exist_ok=True
)

EXPLANATION_DIR = BASE_DIR / "explanations"
EXPLANATION_DIR.mkdir(exist_ok=True)

FRONTEND_FILES = BASE_DIR


# =========================================================
# UPLOAD SETTINGS
# =========================================================

ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
}

ALLOWED_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
}

MAX_FILE_SIZE = (
    10 * 1024 * 1024
)

MIN_WIDTH = 512
MIN_HEIGHT = 512


# =========================================================
# MYSQL CONNECTION
# =========================================================

def mysql_connection(
    with_database=True
):
    """
    Create one MySQL connection.
    """

    settings = {
        "host": MYSQL_HOST,
        "user": MYSQL_USER,
        "password": MYSQL_PASSWORD,
    }

    if with_database:

        settings[
            "database"
        ] = MYSQL_DATABASE

    return mysql.connector.connect(
        **settings
    )


# =========================================================
# DATABASE SETUP
# =========================================================

def setup_database():

    try:

        # -------------------------------------------------
        # Create database
        # -------------------------------------------------

        connection = mysql_connection(
            False
        )

        cursor = connection.cursor()

        cursor.execute(
            f"""
            CREATE DATABASE IF NOT EXISTS
            `{MYSQL_DATABASE}`
            CHARACTER SET utf8mb4
            COLLATE utf8mb4_unicode_ci
            """
        )

        cursor.close()
        connection.close()


        # -------------------------------------------------
        # Connect to RETINOVA database
        # -------------------------------------------------

        connection = mysql_connection(
            True
        )

        cursor = connection.cursor()


        # -------------------------------------------------
        # Users
        # -------------------------------------------------

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (

                id INT AUTO_INCREMENT PRIMARY KEY,

                full_name VARCHAR(120)
                    NOT NULL,

                email VARCHAR(190)
                    NOT NULL UNIQUE,

                password_hash VARCHAR(255)
                    NOT NULL,

                role ENUM(
                    'patient',
                    'doctor',
                    'admin'
                ) NOT NULL,

                created_at
                    TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        # -------------------------------------------------
        # Screenings
        # -------------------------------------------------

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS screenings (

                id INT AUTO_INCREMENT PRIMARY KEY,

                original_filename
                    VARCHAR(255)
                    NOT NULL,

                saved_filename
                    VARCHAR(255)
                    NOT NULL,

                file_size
                    INT
                    NOT NULL,

                width
                    INT
                    NOT NULL,

                height
                    INT
                    NOT NULL,

                quality
                    VARCHAR(30)
                    NOT NULL,

                quality_message
                    VARCHAR(500)
                    NOT NULL,

                created_at
                    TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        # -------------------------------------------------
        # Appointments
        # -------------------------------------------------

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (

                id INT AUTO_INCREMENT PRIMARY KEY,

                patient_id INT,

                doctor_id INT,

                appointment_date
                    DATETIME,

                status
                    VARCHAR(40)
                    DEFAULT 'pending',

                notes TEXT,

                FOREIGN KEY (patient_id)
                    REFERENCES users(id)
                    ON DELETE SET NULL,

                FOREIGN KEY (doctor_id)
                    REFERENCES users(id)
                    ON DELETE SET NULL
            )
            """
        )


        # -------------------------------------------------
        # Reports
        # -------------------------------------------------

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (

                id INT AUTO_INCREMENT PRIMARY KEY,

                screening_id INT,

                patient_id INT,

                doctor_id INT,

                report_text TEXT,

                created_at
                    TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (screening_id)
                    REFERENCES screenings(id)
                    ON DELETE SET NULL,

                FOREIGN KEY (patient_id)
                    REFERENCES users(id)
                    ON DELETE SET NULL,

                FOREIGN KEY (doctor_id)
                    REFERENCES users(id)
                    ON DELETE SET NULL
            )
            """
        )


        # -------------------------------------------------
        # Doctor reviews
        # -------------------------------------------------

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS doctor_reviews (

                id INT AUTO_INCREMENT PRIMARY KEY,

                screening_id INT,

                doctor_id INT,

                decision VARCHAR(80),

                comments TEXT,

                created_at
                    TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (screening_id)
                    REFERENCES screenings(id)
                    ON DELETE SET NULL,

                FOREIGN KEY (doctor_id)
                    REFERENCES users(id)
                    ON DELETE SET NULL
            )
            """
        )


        connection.commit()

        cursor.close()
        connection.close()

        print(
            "MySQL database is ready."
        )


    except Error as exc:

        print(
            "MySQL setup failed:",
            exc
        )

        print(
            "Check MySQL username, password "
            "and database settings."
        )


# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
def startup():

    setup_database()


# =========================================================
# PASSWORD HASHING
# =========================================================

def hash_password(
    password
):
    """
    Salted PBKDF2 password hashing.
    """

    salt = secrets.token_hex(
        16
    )

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(
            "utf-8"
        ),
        salt.encode(
            "utf-8"
        ),
        100_000
    ).hex()

    return (
        f"{salt}${password_hash}"
    )


def check_password(
    password,
    stored_value
):

    try:

        salt, saved_hash = (
            stored_value.split(
                "$",
                1
            )
        )

        test_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(
                "utf-8"
            ),
            salt.encode(
                "utf-8"
            ),
            100_000
        ).hex()

        return secrets.compare_digest(
            test_hash,
            saved_hash
        )

    except ValueError:

        return False


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def clean_filename(
    filename
):

    filename = os.path.basename(
        filename or "image"
    )

    filename = re.sub(
        r"[^A-Za-z0-9_.-]",
        "_",
        filename
    )

    return filename


# =========================================================
# IMAGE QUALITY CHECK
# =========================================================

def check_image_quality(
    image
):
    """
    Basic prototype quality check.

    Fundus datasets commonly contain a circular
    retinal field surrounded by black background.

    Therefore brightness/contrast calculations
    are performed mainly on non-black pixels.

    This is NOT a clinically validated
    image-quality system.
    """

    width, height = image.size


    # -----------------------------------------------------
    # Resolution
    # -----------------------------------------------------

    if (
        width < MIN_WIDTH
        or height < MIN_HEIGHT
    ):

        return {
            "quality": "poor",

            "message": (
                "Image resolution is too small. "
                "Please upload a higher-resolution "
                "fundus image."
            )
        }


    # -----------------------------------------------------
    # Grayscale
    # -----------------------------------------------------

    gray = image.convert(
        "L"
    )


    # -----------------------------------------------------
    # Ignore black background
    # -----------------------------------------------------

    pixels = list(
        gray.getdata()
    )

    retinal_pixels = [
        value
        for value in pixels
        if value > 20
    ]


    # If less than 20% of the image contains
    # non-background pixels, it may not contain
    # a usable retinal field.

    if len(
        retinal_pixels
    ) < (
        width * height * 0.20
    ):

        return {
            "quality": "poor",

            "message": (
                "A sufficiently large retinal "
                "field could not be detected."
            )
        }


    # -----------------------------------------------------
    # Retinal brightness
    # -----------------------------------------------------

    mean_brightness = (
        sum(retinal_pixels)
        / len(retinal_pixels)
    )


    # -----------------------------------------------------
    # Retinal contrast
    # -----------------------------------------------------

    mean = mean_brightness

    variance = sum(
        (
            value - mean
        ) ** 2
        for value in retinal_pixels
    ) / len(retinal_pixels)

    contrast = (
        variance ** 0.5
    )


    # -----------------------------------------------------
    # Basic clarity estimate
    # -----------------------------------------------------

    edge_image = gray.filter(
        ImageFilter.FIND_EDGES
    )

    edge_pixels = [
        value
        for value in edge_image.getdata()
        if value > 10
    ]

    if edge_pixels:

        edge_mean = (
            sum(edge_pixels)
            / len(edge_pixels)
        )

    else:

        edge_mean = 0


    # -----------------------------------------------------
    # IMPORTANT
    #
    # Do NOT reject normal retinal images merely
    # because they are dark/orange or have low
    # global contrast.
    #
    # We use these values only for a very basic
    # warning condition.
    # -----------------------------------------------------

    problems = []


    if mean_brightness < 15:

        problems.append(
            "retinal field is extremely dark"
        )


    if mean_brightness > 250:

        problems.append(
            "retinal field is extremely bright"
        )


    # Only reject severely unusable cases.
    # Normal APTOS-style fundus photographs
    # should pass.

    if (
        contrast < 3
        and edge_mean < 0.5
    ):

        problems.append(
            "image may contain very little "
            "visible retinal information"
        )


    if problems:

        return {
            "quality": "poor",

            "message": (
                "Image quality may be insufficient: "
                + "; ".join(problems)
                + "."
            )
        }


    return {
        "quality": "acceptable",

        "message": (
            "Image is suitable for further analysis."
        )
    }


# =========================================================
# REQUEST MODELS
# =========================================================

class SignupRequest(
    BaseModel
):

    full_name: str
    email: str
    password: str
    role: str


class LoginRequest(
    BaseModel
):

    email: str
    password: str


# =========================================================
# AI MODEL
# =========================================================

MODEL_PATH = (
    BASE_DIR
    / "models"
    / "retinova_resnet18.pth"
)


AI_DEVICE = torch.device(
    "cuda"
    if torch.cuda.is_available()
    else "cpu"
)


ai_model = models.resnet18(
    weights=None
)


# Five DR classes
ai_model.fc = nn.Linear(
    ai_model.fc.in_features,
    5
)


if not MODEL_PATH.exists():

    raise FileNotFoundError(
        "AI model file was not found:\n"
        f"{MODEL_PATH}"
    )


ai_model.load_state_dict(
    torch.load(
        MODEL_PATH,
        map_location=AI_DEVICE
    )
)


ai_model = ai_model.to(
    AI_DEVICE
)

ai_model.eval()


DR_CLASSES = [
    "No DR",
    "Mild",
    "Moderate",
    "Severe",
    "Proliferative"
]


# Selected using validation data.
REFERABLE_THRESHOLD = 0.05


print(
    "AI model loaded successfully."
)

print(
    "AI device:",
    AI_DEVICE
)

print(
    "AI model path:",
    MODEL_PATH
)


# =========================================================
# AI IMAGE ANALYSIS
# =========================================================

def analyze_image(
    image_path
):

    """
    Run the trained ResNet18 model.

    Training input:
        224 x 224 RGB

    Normalization:
        ImageNet mean/std

    Referable DR:
        classes 2, 3 and 4
    """

    ai_transform = transforms.Compose(
        [

            transforms.Resize(
                (224, 224)
            ),

            transforms.ToTensor(),

            transforms.Normalize(
                mean=[
                    0.485,
                    0.456,
                    0.406
                ],

                std=[
                    0.229,
                    0.224,
                    0.225
                ]
            )
        ]
    )


    image = Image.open(
        image_path
    ).convert(
        "RGB"
    )


    ai_input = ai_transform(
        image
    ).unsqueeze(
        0
    ).to(
        AI_DEVICE
    )


    with torch.no_grad():

        output = ai_model(
            ai_input
        )


        probabilities = torch.softmax(
            output,
            dim=1
        )


        predicted_class = torch.argmax(
            probabilities,
            dim=1
        ).item()


        ai_confidence = probabilities[
            0,
            predicted_class
        ].item()


        # Classes:
        # 0 = No DR
        # 1 = Mild
        # 2 = Moderate
        # 3 = Severe
        # 4 = Proliferative
        #
        # Referable = classes 2, 3, 4

        referable_probability = probabilities[
            0,
            2:
        ].sum().item()


    ai_prediction = (
        DR_CLASSES[
            predicted_class
        ]
    )


    ai_referable = (
        referable_probability
        >= REFERABLE_THRESHOLD
    )


    return {

        "prediction":
            ai_prediction,

        "confidence":
            round(
                ai_confidence * 100,
                2
            ),

        "referable_dr":
            ai_referable,

        "referable_probability":
            round(
                referable_probability * 100,
                2
            ),

        "class_index":
            predicted_class
    }


# =========================================================
# SIMPLE MANUAL GRAD-CAM
# =========================================================

def generate_gradcam(image_path, output_path, target_class=None):
    """Generate a Grad-CAM overlay using the final ResNet18 block.

    This implementation avoids an extra Grad-CAM dependency so the
    demo can run with the already-installed PyTorch/torchvision stack.
    """

    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ])

    original = Image.open(image_path).convert("RGB")
    input_tensor = transform(original).unsqueeze(0).to(AI_DEVICE)

    activations = []
    gradients = []

    def forward_hook(module, inputs, output):
        activations.append(output)

    def backward_hook(module, grad_input, grad_output):
        gradients.append(grad_output[0])

    target_layer = ai_model.layer4[-1]
    fh = target_layer.register_forward_hook(forward_hook)
    bh = target_layer.register_full_backward_hook(backward_hook)

    try:
        ai_model.zero_grad(set_to_none=True)
        output = ai_model(input_tensor)
        if target_class is None:
            target_class = int(torch.argmax(output, dim=1).item())

        score = output[0, target_class]
        score.backward()

        if not activations or not gradients:
            raise RuntimeError("Grad-CAM hooks did not capture activations/gradients.")

        activation = activations[-1].detach()[0]
        gradient = gradients[-1].detach()[0]

        weights = gradient.mean(dim=(1, 2))
        cam = torch.sum(weights[:, None, None] * activation, dim=0)
        cam = torch.relu(cam)
        cam = cam - cam.min()
        cam = cam / (cam.max() + 1e-8)

        cam_np = cam.cpu().numpy()
        cam_img = Image.fromarray(
            np.uint8(cam_np * 255),
            mode="L",
        ).resize(original.size, Image.Resampling.BILINEAR)

        heat = np.asarray(cam_img).astype(np.float32) / 255.0
        rgb = np.asarray(original).astype(np.float32) / 255.0

        # Simple blue -> cyan -> yellow -> red heatmap.
        r = np.clip(1.5 * heat, 0, 1)
        g = np.clip(1.5 * (1 - np.abs(heat - 0.5) * 2), 0, 1)
        b = np.clip(1.5 * (1 - heat), 0, 1)
        heat_rgb = np.stack([r, g, b], axis=2)

        alpha = (heat ** 1.2)[..., None] * 0.45
        overlay = np.clip(
            rgb * (1 - alpha) + heat_rgb * alpha,
            0,
            1,
        )

        result = Image.fromarray(
            np.uint8(overlay * 255),
            mode="RGB",
        )
        result.save(output_path, quality=92)

    finally:
        fh.remove()
        bh.remove()
        ai_model.zero_grad(set_to_none=True)




# =========================================================
# HEALTH
# =========================================================

@app.get(
    "/api/health"
)
def health():

    return {

        "status":
            "online",

        "project":
            "RETINOVA",

        "ai_status":
            "connected"

    }


# =========================================================
# SIGNUP
# =========================================================

@app.post(
    "/api/auth/signup"
)
def signup(
    data: SignupRequest
):

    full_name = (
        data.full_name.strip()
    )

    email = (
        data.email.strip().lower()
    )

    role = (
        data.role.strip().lower()
    )


    if not full_name:

        raise HTTPException(
            status_code=400,
            detail=(
                "Full name is required."
            )
        )


    if role not in {
        "patient",
        "doctor",
        "admin"
    }:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid role."
            )
        )


    if len(
        data.password
    ) < 6:

        raise HTTPException(
            status_code=400,
            detail=(
                "Password must contain "
                "at least 6 characters."
            )
        )


    try:

        connection = mysql_connection()

        cursor = connection.cursor(
            dictionary=True
        )


        cursor.execute(
            """
            SELECT id
            FROM users
            WHERE email = %s
            """,

            (
                email,
            )
        )


        if cursor.fetchone():

            cursor.close()
            connection.close()

            raise HTTPException(
                status_code=409,
                detail=(
                    "An account with this "
                    "email already exists."
                )
            )


        cursor.execute(
            """
            INSERT INTO users
            (
                full_name,
                email,
                password_hash,
                role
            )

            VALUES
            (
                %s,
                %s,
                %s,
                %s
            )
            """,

            (
                full_name,
                email,
                hash_password(
                    data.password
                ),
                role
            )
        )


        connection.commit()

        user_id = (
            cursor.lastrowid
        )


        cursor.close()
        connection.close()


        user = {

            "id":
                user_id,

            "name":
                full_name,

            "role":
                role

        }


        session_id = (
            secrets.token_urlsafe(
                32
            )
        )


        sessions[
            session_id
        ] = user


        response = JSONResponse(
            {
                "success":
                    True,

                "user":
                    user
            }
        )


        response.set_cookie(
            "retinova_session",

            session_id,

            httponly=True,

            samesite="lax",

            max_age=8 * 60 * 60
        )


        return response


    except HTTPException:

        raise


    except Error as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Database error: {exc}"
            )
        )


# =========================================================
# LOGIN
# =========================================================

@app.post(
    "/api/auth/login"
)
def login(
    data: LoginRequest
):

    email = (
        data.email.strip().lower()
    )


    try:

        connection = mysql_connection()

        cursor = connection.cursor(
            dictionary=True
        )


        cursor.execute(
            """
            SELECT
                id,
                full_name,
                email,
                password_hash,
                role
            FROM users
            WHERE email = %s
            """,

            (
                email,
            )
        )


        user = (
            cursor.fetchone()
        )


        cursor.close()
        connection.close()


        if (
            not user
            or not check_password(
                data.password,
                user[
                    "password_hash"
                ]
            )
        ):

            raise HTTPException(
                status_code=401,
                detail=(
                    "Invalid email "
                    "or password."
                )
            )


        logged_in_user = {

            "id":
                user["id"],

            "name":
                user["full_name"],

            "role":
                user["role"]

        }


        session_id = (
            secrets.token_urlsafe(
                32
            )
        )


        sessions[
            session_id
        ] = logged_in_user


        response = JSONResponse(
            {
                "success":
                    True,

                "user":
                    logged_in_user
            }
        )


        response.set_cookie(
            "retinova_session",

            session_id,

            httponly=True,

            samesite="lax",

            max_age=8 * 60 * 60
        )


        return response


    except HTTPException:

        raise


    except Error as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Database error: {exc}"
            )
        )


# =========================================================
# LOGOUT
# =========================================================

@app.post(
    "/api/auth/logout"
)
def logout(
    request: Request
):

    session_id = (
        request.cookies.get(
            "retinova_session"
        )
    )


    if session_id:

        sessions.pop(
            session_id,
            None
        )


    response = JSONResponse(
        {
            "success":
                True
        }
    )


    response.delete_cookie(
        "retinova_session"
    )


    return response


# =========================================================
# IMAGE UPLOAD + AI
# =========================================================

@app.post(
    "/api/upload"
)
async def upload_image(
    request: Request,
    file: UploadFile = File(...)
):

    # -----------------------------------------------------
    # Authentication
    # -----------------------------------------------------

    session_id = (
        request.cookies.get(
            "retinova_session"
        )
    )


    user = (
        sessions.get(
            session_id
        )
    )


    if not user:

        raise HTTPException(
            status_code=401,
            detail=(
                "Please log in before "
                "uploading an image."
            )
        )


    if user["role"] != "patient":

        raise HTTPException(
            status_code=403,
            detail=(
                "Only patients can "
                "upload screening images."
            )
        )


    # -----------------------------------------------------
    # Filename
    # -----------------------------------------------------

    original_name = (
        clean_filename(
            file.filename
        )
    )


    extension = (
        Path(
            original_name
        ).suffix.lower()
    )


    if (
        extension
        not in ALLOWED_EXTENSIONS
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Accepted formats: "
                "JPG, JPEG, PNG."
            )
        )


    if (
        file.content_type
        and file.content_type
        not in ALLOWED_TYPES
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded file "
                "is not a JPG, JPEG "
                "or PNG image."
            )
        )


    # -----------------------------------------------------
    # Read file
    # -----------------------------------------------------

    contents = (
        await file.read()
    )


    if not contents:

        raise HTTPException(
            status_code=400,
            detail=(
                "The uploaded file "
                "is empty."
            )
        )


    if (
        len(contents)
        > MAX_FILE_SIZE
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Image is too large. "
                "Maximum size is 10 MB."
            )
        )


    # -----------------------------------------------------
    # Validate actual image
    # -----------------------------------------------------

    try:

        image = Image.open(
            BytesIO(contents)
        )

        image.verify()


        image = Image.open(
            BytesIO(contents)
        )


        width, height = (
            image.size
        )


        quality_result = (
            check_image_quality(
                image
            )
        )


    except (
        UnidentifiedImageError,
        OSError
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "The file is not "
                "a valid image."
            )
        )


    # -----------------------------------------------------
    # Save image
    # -----------------------------------------------------

    safe_name = (
        f"{uuid.uuid4().hex}"
        f"{extension}"
    )


    save_path = (
        UPLOAD_DIR
        / safe_name
    )


    save_path.write_bytes(
        contents
    )


    # -----------------------------------------------------
    # AI prediction
    # -----------------------------------------------------

    try:

        ai_result = (
            analyze_image(
                str(save_path)
            )
        )

        explanation_name = (
            f"{save_path.stem}_gradcam.jpg"
        )

        explanation_path = (
            EXPLANATION_DIR
            / explanation_name
        )

        generate_gradcam(
            str(save_path),
            str(explanation_path),
            target_class=ai_result["class_index"]
        )

    except Exception as exc:

        print(
            "AI prediction failed:",
            exc
        )


        try:

            save_path.unlink()

        except OSError:

            pass


        raise HTTPException(
            status_code=500,
            detail=(
                f"AI analysis failed: {exc}"
            )
        )


    # -----------------------------------------------------
    # Save screening record
    # -----------------------------------------------------

    screening_id = None


    try:

        connection = (
            mysql_connection()
        )

        cursor = (
            connection.cursor()
        )


        cursor.execute(
            """
            INSERT INTO screenings
            (
                original_filename,
                saved_filename,
                file_size,
                width,
                height,
                quality,
                quality_message
            )

            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,

            (
                original_name,

                safe_name,

                len(contents),

                width,

                height,

                quality_result[
                    "quality"
                ],

                quality_result[
                    "message"
                ]
            )
        )


        connection.commit()


        screening_id = (
            cursor.lastrowid
        )


        cursor.close()
        connection.close()


    except Error as exc:

        print(
            "Screening database insert failed:",
            exc
        )


    # -----------------------------------------------------
    # API response
    # -----------------------------------------------------

    return {

        "success":
            True,

        "filename":
            original_name,

        "saved_filename":
            safe_name,

        "file_size":
            len(contents),

        "width":
            width,

        "height":
            height,

        "quality":
            quality_result[
                "quality"
            ],

        "quality_message":
            quality_result[
                "message"
            ],

        "screening_id":
            screening_id,

        "ai_status":
            "AI model connected",

        "ai_prediction":
            ai_result[
                "prediction"
            ],

        "ai_confidence":
            ai_result[
                "confidence"
            ],

        "referable_dr":
            ai_result[
                "referable_dr"
            ],

        "referable_probability":
            ai_result[
                "referable_probability"
            ],

        "referable_threshold":
            REFERABLE_THRESHOLD,

        "explanation_url":
            f"/explanations/{explanation_name}"
    }


# =========================================================
# SERVE EXPLANATIONS
# =========================================================

app.mount(
    "/explanations",
    StaticFiles(
        directory=str(EXPLANATION_DIR)
    ),
    name="explanations"
)


# =========================================================
# SERVE FRONTEND
# =========================================================

app.mount(
    "/",
    StaticFiles(
        directory=str(
            FRONTEND_FILES
        ),
        html=True
    ),
    name="frontend"
)
