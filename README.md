# SavrenAI

SavrenAI is a desktop app that lets you chat with an AI that can read
files, run commands, and write code on your own computer. This page gets
you from nothing to talking to it in about ten minutes. No programming
knowledge needed.

## What you need

- A computer with an internet connection.
- An OpenCode Go account (free). You will create one in Step 3.

## Step 1: Download the app

1. Open your web browser (Safari, Chrome, Edge, or Firefox).
2. Click the address bar at the top of the window.
3. Type exactly this and press Enter:

   `github.com/mytechnotalent/SavrenAI/releases`

4. At the top of the page, find the newest release (the one marked
   "Latest").
5. Scroll down to "Assets" and click the file for your computer:

   - **Mac** (the computer with an Apple logo) -> click
     `SavrenAI-macos-arm64.zip`
   - **Windows PC** -> click `SavrenAI-windows.zip`
   - **Linux** -> click `SavrenAI-linux.zip`

The file lands in your **Downloads** folder.

## Step 2: Unpack it

- **Windows**: open the Downloads folder, right-click
  `SavrenAI-windows.zip`, choose **Extract All...**, then click
  **Extract**. A folder named `SavrenAI` appears.
- **Mac**: double-click `SavrenAI-macos-arm64.zip` in Downloads. A
  `SavrenAI.app` appears. Drag it into your **Applications** folder.
- **Linux**: right-click `SavrenAI-linux.zip` and choose **Extract
  Here**.

## Step 3: Create an OpenCode Go account and get your key

1. In your browser, go to `opencode.ai/console`.
2. Click **Sign up** (or log in if you already have an account).
3. Look for the **API keys** page or section.
4. Click **Create API key** (or **New key**).
5. Copy the key. It is one long line of text that starts with `oc_sk`.
   Keep this browser tab open so you can copy it again if needed.

A key is a secret password for your account. Treat it like a bank PIN and
never send it to anyone.

## Step 4: Make your settings file

Every SavrenAI download includes a file named `.env.example`. It becomes
your settings file when you rename it to `.env`.

**Windows**

1. Open the `SavrenAI` folder you extracted in Step 2.
2. Right-click the file named `.env.example` and choose **Rename**.
3. Type `.env` and press Enter.
   - If the name becomes `.env.txt`, open the folder menu **View**, tick
     **File name extensions**, and rename it again.
4. Right-click `.env` and choose **Open with -> Notepad**.

**Mac**

1. In Applications, right-click `SavrenAI.app` and choose **Show Package
   Contents**. Open the `Contents` folder, then the `MacOS` folder.
2. Rename `.env.example` to `.env`.
3. Open `.env` with **TextEdit**. If the file opens with fancy formatting,
   use the menu **Format -> Make Plain Text**.

**Linux**

1. In the extracted folder, rename `.env.example` to `.env`.
2. Open `.env` with any text editor.

**Then, in the `.env` file you just opened, do these three edits:**

1. Find the first line that says `HARNESS_PROVIDER=openrouter` and change
   it so it reads exactly:

   `HARNESS_PROVIDER=opencode`

2. Find the line `OPENCODE_API_KEY=` and paste your key right after the
   equals sign, with no spaces. It will look like:

   `OPENCODE_API_KEY=oc_sk...`

3. Find the line `OPENCODE_MODEL=deepseek-v4.1-flash` and leave it exactly
   as it is. This is the free model the app will use.

Save the file (Ctrl+S on Windows or Linux, Command+S on Mac) and close it.

## Step 5: Open the app

- **Windows**: double-click `SavrenAI.exe` inside the `SavrenAI` folder.
  If a blue window says "Windows protected your PC", click **More
  info**, then **Run anyway**.
- **Mac**: open `SavrenAI.app` from Applications. If a message says the
  app "cannot be opened", right-click (or hold Control and click) the
  app and choose **Open**, then **Open** again. You only do this once.
- **Linux**: double-click the `SavrenAI` file.

The first open can take a few seconds. A chat window appears.

## Step 6: Talk to it

Click the box at the bottom of the window, type a question, and press
Enter. Try this one:

`Make a folder called notes and write a file inside it that says hello`

The AI reads and writes files on your computer, so it can do real work for
you.

## If something goes wrong

- **"Where is my key?"** Go back to `opencode.ai/console`, open the API
  keys page, and copy the key again.
- **The app says the API key is not set.** Your `.env` file is probably
  named wrong (it must be exactly `.env`) or the key line has a space in
  it. Redo Step 4.
- **The app will not open on Windows.** Redo the "More info -> Run
  anyway" step from Step 5.
- **The app will not open on Mac.** Redo the right-click Open step from
  Step 5.

## For developers

Everything else - how the harness works, how to build it from source, how
to run the tests, and the evaluation results - lives in
[AGENTS.md](AGENTS.md) and the [docs](docs) folder.
