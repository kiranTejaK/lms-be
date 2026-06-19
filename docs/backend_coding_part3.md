# Backend Coding: Advanced Real-World Scenarios
*(Part 3: S3 Presigned URLs, Data Migrations, and Graceful Shutdowns)*

---

## 1. Expected Coding & Scaffold Questions

### Question 12: AWS S3 Presigned URLs for File Uploads
**Prompt:** You are building a course platform where instructors upload 1GB video files. If they upload directly to your FastAPI backend, your server will lock up handling massive payload streams. Write a FastAPI endpoint that generates an AWS S3 Presigned URL, allowing the frontend to upload the file directly to S3.

**Deep Level Understanding:** Direct uploads to your backend consume server CPU, memory, and bandwidth. By using a Presigned URL, your backend acts merely as the "gatekeeper." It generates a temporary, cryptographically signed URL with a short expiration time (e.g., 15 minutes) and hands it to the frontend. The frontend then handles the heavy lifting by performing a `PUT` request directly to AWS S3.

**Expected Scaffold Answer:**
```python
import boto3
from fastapi import APIRouter, Depends, HTTPException
from botocore.exceptions import ClientError
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()

# Initialize S3 client (usually this goes in a core config or service)
s3_client = boto3.client(
    's3',
    aws_access_key_id="YOUR_KEY",
    aws_secret_access_key="YOUR_SECRET",
    region_name="us-east-1"
)

@router.get("/courses/upload-url")
def get_upload_url(
    filename: str, 
    file_type: str, 
    current_user: User = Depends(get_current_user)
):
    """
    Generates a presigned URL that the frontend can use to upload a file
    directly to S3.
    """
    bucket_name = "my-course-videos-bucket"
    # Create a unique object key to prevent users from overwriting each other's files
    object_key = f"uploads/{current_user.id}/{filename}"
    
    try:
        # Generate the presigned URL for a PUT request
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': object_key,
                'ContentType': file_type # Ensure frontend sends matching content-type
            },
            ExpiresIn=900 # URL expires in 15 minutes (900 seconds)
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail="Could not generate upload URL")

    # Return the URL and the object key so the frontend can save the key in the DB later
    return {
        "upload_url": presigned_url,
        "object_key": object_key
    }
```

### Question 13: Alembic Data Migration in Batches
**Prompt:** You need to split a `full_name` column into `first_name` and `last_name` columns on a `users` table with 5 million rows. Write a Python script (as would appear in an Alembic migration) to migrate this data safely without locking the entire table.

**Deep Level Understanding:** Running `UPDATE users SET first_name = ...` on 5 million rows will acquire a heavy write lock, preventing users from logging in or registering while it processes. Instead, you must paginate through the database using a cursor or ID range and commit updates in small batches (e.g., 1,000 rows at a time).

**Expected Scaffold Answer:**
```python
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

def upgrade():
    # 1. Add the new columns as nullable first
    op.add_column('users', sa.Column('first_name', sa.String(), nullable=True))
    op.add_column('users', sa.Column('last_name', sa.String(), nullable=True))
    
    # 2. Grab the DB session to perform data operations
    bind = op.get_bind()
    session = Session(bind=bind)
    
    # We use a raw text query or core execution for performance
    # Let's assume we use an ID-based chunking strategy
    
    batch_size = 1000
    last_id = 0
    
    while True:
        # Fetch the next batch of users who haven't been processed yet
        # Ordering by ID guarantees we don't miss rows and can resume easily
        result = session.execute(
            sa.text(
                "SELECT id, full_name FROM users WHERE id > :last_id ORDER BY id ASC LIMIT :limit"
            ),
            {"last_id": last_id, "limit": batch_size}
        ).fetchall()
        
        if not result:
            break # No more users to process
            
        # Process and update this batch
        for user_id, full_name in result:
            last_id = user_id # Remember the last ID processed
            
            if full_name:
                parts = full_name.split(" ", 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ""
                
                session.execute(
                    sa.text(
                        "UPDATE users SET first_name = :first, last_name = :last WHERE id = :id"
                    ),
                    {"first": first_name, "last": last_name, "id": user_id}
                )
                
        # Commit after EVERY batch to release row locks and save memory
        session.commit()
        print(f"Processed up to user ID: {last_id}")

def downgrade():
    op.drop_column('users', 'first_name')
    op.drop_column('users', 'last_name')
```

### Question 14: Graceful Shutdown in FastAPI
**Prompt:** Your application is deployed in a Docker container. When the container orchestrator (like Kubernetes) scales down or updates the app, it sends a `SIGTERM` signal. How do you configure FastAPI to handle this signal and ensure running tasks or active database queries complete gracefully instead of hard-killing them?

**Deep Level Understanding:** By default, a sudden stop can leave database transactions dangling, files half-written, or network requests dropped. FastAPI uses the `lifespan` async context manager to handle startup and shutdown logic. You can use it to finish background processing or clean up external connections.

**Expected Scaffold Answer:**
```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI

# Imagine this is a task queue running in memory or a long process
active_background_tasks = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP LOGIC ---
    print("Application starting up: Initializing resources...")
    # e.g., setup DB pool, connect to Redis
    
    yield
    
    # --- SHUTDOWN LOGIC ---
    print("SIGTERM/SIGINT received: Starting graceful shutdown...")
    
    # 1. Stop accepting new tasks or background work
    # 2. Wait for all currently running background tasks in our set to complete
    if active_background_tasks:
        print(f"Waiting for {len(active_background_tasks)} background tasks to finish...")
        # Wait up to 10 seconds for tasks to clear
        try:
            await asyncio.wait_for(
                asyncio.gather(*active_background_tasks), 
                timeout=10.0
            )
        except asyncio.TimeoutError:
            print("Shutdown timed out: Some tasks were forcefully killed.")
            
    # 3. Close database pools and Redis connections
    # await db_pool.close()
    # await redis.disconnect()
    print("Clean shutdown complete.")

# Apply the lifespan to the FastAPI app
app = FastAPI(lifespan=lifespan)

@app.post("/do-heavy-work")
async def trigger_task():
    task = asyncio.create_task(heavy_computation())
    # Add to our tracker set so the lifespan knows to wait for it
    active_background_tasks.add(task)
    # Remove it when it finishes to prevent memory leaks
    task.add_done_callback(active_background_tasks.discard)
    return {"status": "Task started"}

async def heavy_computation():
    await asyncio.sleep(5) # Simulating a 5 second job
    print("Heavy work finished!")
```
