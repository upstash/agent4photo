## Features
- **Fetch Unseen Emails**: Connects to an IMAP server, retrieves unread emails, and extracts text and images.
- **Process Text with OpenAI**: Uses GPT-4 to analyze email content and extract structured information.
- **Enhance Images with Fal.ai**: Uploads images from emails to Fal.ai for processing.
- **Send Processed Results via Email**: Returns processed images and text to the sender.


You can see the full code available at main.py file. Below the basics of Workflow and Vercel, along with their usages in this project, will be explained.

## Setup & Installation

### **Environment Variables**
If you are working on your local, create a `.env` file. Otherwise, set your variables on your Vercel project page's settings tab. 

```env
IMAP_SERVER=your-imap-server
EMAIL_ADDRESS=your-email@example.com
...
```

_In order to use Upstash Workflow, visit your console at Upstash, copy your QSTASH_TOKEN and set as environment variable._
### **Install Dependencies**
Ensure you have Python installed, then install the required packages.

```sh
pip install requirements.txt
```

If you are using Vercel, to have requirements.txt file on your deployment is enough. 

## Implementation

### Creating FastAPI APP

```python
from fastapi import FastAPI

# Create FastAPI instance
app = FastAPI()

# Checking the environment variables
@app.get("/")
def read_root():

    key = os.getenv("CHECK_KEY")
    return {"key": key}
```

### Creating Upstash Workflow
Use the serve method to define an endpoint that serves a workflow. It provides a context object that you use to create all of your workflow’s steps.

```python
from upstash_workflow.fastapi import Serve
from upstash_workflow import AsyncWorkflowContext, CallResponse

app = FastAPI()
serve = Serve(app)

@serve.post("/fal")
async def fal_wf(context: AsyncWorkflowContext):
...
```

In this function, context variable will hold the request payload, which we do not have any for this example, provide utilities such as .run, .call or .sleep.

### Using a Function Inside the Workflow

You can define your functions outside of the workflow. 

```python
def send_email(sender, image_url, success):
  ...
  # See the main.py for the real implementation of this function.
  ...

@serve.post("/fal")
async def fal_wf(context: AsyncWorkflowContext):
  ...
  ...
  async def _send_email():
      return send_email(sender, output_url, True)

  await context.run("send-email", _send_email)
```

Use context.run to use a method that is defined outside of the workflow. It is highly recommended to use context.run's for almost all the logic you implement in your code.

### Making Requests 

If you think your request can take more than a few seconds, it is better to use context.call. This way, we can exceed the time limit of Vercel. 

```python
@serve.post("/fal")
async def fal_wf(context: AsyncWorkflowContext):
  ...
  ...

  # Making a request to fal.ai for image processing
  response2 = await context.call(
      "process-image-fal",  # Workflow step-name
      url = "https://queue.fal.run/fal-ai/clarity-upscaler",  # URL
      method = "POST",  
      body = input_dict,
      headers = {
          "authorization": f"Key {FAL_KEY}",
          "Content-Type": "application/json",
      })

  if response2.status == 200:
      status_url = response2.body["status_url"]
      response_url = response2.body["response_url"]
  
  ...

```

Note that this is the equivalent of python code below:

```python
response = requests.post(
    "https://queue.fal.run/fal-ai/clarity-upscaler",
    headers= {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"},
    data= json.dumps(input_dict))
```

But it is recommended to use context.call in Workflow. 

### Waiting

If for some reason you need to wait, you can use context.sleep.

```python
    # Wait for 1 minute while the image is getting processed
    await context.sleep("wait-for-fal-response", "1m")
```

In our example, we are creating a run request like we did above. But for image to be processed, 5 to 40 seconds is needed. Just like time.sleep() in Python,
we use context.sleep which stalls the workflow for the time specified. 


## Deploying to Vercel

Once your code is ready, you can deploy it on Vercel.

Before you start deployment, create a vercel.json in your project folder to specify build configuration. For our project structure, the vercel.json file looks like this:

```json
{
    "version": 2,
    "builds": [
      {
        "src": "main.py",
        "use": "@vercel/python"
      }
    ],
    "routes": [
      {
        "src": "/(.*)",
        "dest": "main.py"
      }
    ]
  }
```

Open your terminal. 

```sh
npm install -g vercel # Installing vercel
cd path/to/your/project/folder # Navigate to your project folder
vercel
```

After a couple of seconds, you will be able to see your deployment on Vercel.

You can try your deployment by sending a request like this:

```sh
curl -X POST "https://your-vercel-project-7ee79bd2.vercel.app/fal"
```
