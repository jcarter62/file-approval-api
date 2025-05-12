from asyncio import wait_for
from fastapi import FastAPI
import uvicorn
import os
import shutil
from dotenv import load_dotenv
import json
from fpdf import FPDF  # Add this import
from PyPDF2 import PdfMerger, PdfWriter  # Add this import
from datetime import datetime
import schedule
import time
from emailsender import EmailSender

# Load environment variables from .env file
load_dotenv()
# app = FastAPI()

debug_mode = (os.getenv("DEBUG", "False") == "True")
sleep_time = int(os.getenv("SLEEP_TIME", 60))
exec_every_seconds = int(os.getenv("EXEC_EVERY_SECONDS", 60))


def calculate_account_folder(account_id: str) -> str:
    """
    Calculate the account folder path based on the account ID.
    """
    # convert account_id to zero padded string 10 characters long
    account_id = str(account_id).zfill(10)
    # Ensure the account_id is 10 characters long
    if len(account_id) != 10:
        raise ValueError("Account ID must be 10 characters long.")
    # split the account_id into 5 parts separated by /
    account_id = os.path.join(account_id[:2], account_id[2:4], account_id[4:6], account_id[6:8], account_id[8:])
    # Ensure the base path is set
    base_dest = os.getenv("BASE_DEST", None)
    if not base_dest:
        raise ValueError("BASE_DEST environment variable is not set.")

    account_folder = os.path.join(base_dest, account_id)
    return account_folder


def move_to_account_folder(file_path: str, account_id: str):
    """
    Move the file to the account folder.
    """
    try:
        results = False
        dest_folder = calculate_account_folder(account_id)
        if not os.path.exists(dest_folder):
            os.makedirs(dest_folder)
        new_file_path = os.path.join(dest_folder, os.path.basename(file_path))
        shutil.move(file_path, new_file_path)
        if os.path.exists(new_file_path):
            results = True
    except Exception as e:
        print(f"Error moving file: {str(e)}")
        results = False
    return results

def read_file_text(file_path: str) -> str:
    """
    Read the text from the file, and return it.
    """
    try:
        base_path = os.getenv("BASE_PATH", "/tmp")
        pth = os.path.join(base_path, file_path)
        text = ''
        with open(pth, "r") as f:
            text = text + f.read()
        text = text + '\n' + '----------------------------------------\n'
        #                     123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890
        #                              1         2         3         4         5         6         7         8         9
    except Exception as e:
        print(f"Error reading file: {str(e)}")
    return text

def approve(id: str):
    result_text = ''
    continue_flag = True
    file_path = ''
    base_path = ''
    try:
        base_path = os.getenv("BASE_PATH", "/tmp")
        file_path = os.path.join(base_path, f"{id}.json")
        #
        # check if the file exists
        #
        if not os.path.exists(file_path):
            result_text = f"File {file_path} does not exist."
            continue_flag = False
    except Exception as e:
        result_text = f"Error: {str(e)}"
        continue_flag = False

    pdf = FPDF()
    merger = PdfMerger()
    data = {}
    approved_flag = False

    if continue_flag:
        try:
            #
            # load json file
            #
            with open(file_path, "r") as f:
                jdata = f.read()
            #
            # convert json to dict
            data = json.loads(jdata)
            #
            # load the text file specified by data['response']
            #
            tfiles = os.listdir(os.getenv("BASE_PATH", "/tmp"))
            tfiles = [f for f in tfiles if f.endswith(".txt") and f.startswith(data["id"])]
            # sort tfiles by name
            tfiles.sort()
            response_file = ''

            for f in tfiles:
                if debug_mode:
                    print(f"Processing file: {f}")
                # read the text file
                response_file = response_file + read_file_text(f)

            # for each response file, search for line starting with 'response:' check the next word
            # if it is 'approve*' then set approved_flag = True
            # otherwise set approved_flag = False
            for f in tfiles:
                if debug_mode:
                    print(f"Processing file: {f}")
                # read the text file
                tf_path = os.path.join(base_path, f)
                with open(tf_path, "r") as tf:
                    lines = tf.readlines()
                    for line in lines:
                        ln = line.lower()
                        if ln.lower().startswith("response:"):
                            response = ln.split(":")[1].strip()
                            if response.startswith("approve"):
                                approved_flag = True
                            else:
                                approved_flag = False

            #
            # now,
            # 1. convert data.response to temp pdf,
            # 2. combine data.file and temp pdf,
            # 3. save to data.result
            #
            temp_pdf_path = os.path.join(base_path, f"{id}_temp.pdf")
            pdf.add_page()
            # Create a PDF document
            pdf.set_font(family="Courier", style="", size=12)
            pdf.multi_cell(w=0,h=8, txt=response_file)  # Write the response text to the PDF
            pdf.output( temp_pdf_path)
            pdf.close()
            pdf = None

            # Now we have a temp PDF file at temp_pdf_path
            # You can implement the logic to combine the original data.file and the temp PDF here
            # For example, you might want to use PyPDF2 or similar library to merge PDFs

            # Add the original data.file PDF
            original_pdf_path = os.path.join(base_path, data["id"] + '.pdf')
            merger.append(original_pdf_path)
            # Add the temp PDF
            merger.append(temp_pdf_path)
            # Save the merged PDF to the result path
            result_pdf_path = os.path.join(base_path, data["id"] + '-result.pdf')
            # remove the result file if it exists
            if os.path.exists(result_pdf_path):
                os.remove(result_pdf_path)
            merger.write(result_pdf_path)
            merger.close()
            merger = None
            # Clean up the temp PDF file
            os.remove(temp_pdf_path)
        except Exception as e:
            result_text = f"Error: {str(e)}"
            print(result_text)
            if merger:
                merger.close()
                merger = None
            if pdf:
                pdf.close()
                pdf = None
        # continue_flag

    if continue_flag:
        continue_flag, result_text = move_results_to_account_folder(continue_flag, data, result_text)

    # rename file based on data['saveas']
    save_as_path = ''
    if continue_flag:
        continue_flag, result_text, save_as_path = rename_dest_file(continue_flag, data, result_text, approved_flag)

    if continue_flag:
        # send_email(filename: str, email_address: str, account: str, state: str, name: str):
        state = 'approved' if approved_flag else 'rejected'
        send_email(save_as_path, os.getenv("MAIL_TO", ""), data["account"],
                   state, data["saveas"])

    if continue_flag:
        result_text = remove_temp_files(data, result_text)

    return {"message": f"{id} -- {result_text}"}

def remove_temp_files(data, result_text):
    try:
        # remove temp files for this id
        # for files with name containing id, remove them
        base_path = os.getenv("BASE_PATH", "/tmp")

        temp_files = [f for f in os.listdir(base_path) if f.startswith(data['id'])]
        for temp_file in temp_files:
            temp_file_path = os.path.join(base_path, temp_file)
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    except Exception as e:
        result_text = f"Error: {str(e)}"
        print(result_text)
        continue_flag = False
    return result_text

def move_results_to_account_folder(continue_flag, data, result_text):
    try:
        # move the result file to the account folder
        account_id = data["account"]
        base_path = os.getenv("BASE_PATH", "/tmp")
        result_file_path = os.path.join(base_path, data["id"] + '-result.pdf')
        move_results = move_to_account_folder(result_file_path, account_id)
        if not move_results:
            continue_flag = False
            result_text = f"Error moving file to account folder."
    except Exception as e:
        result_text = f"Error: {str(e)}"
        continue_flag = False
    return continue_flag, result_text

def rename_dest_file(continue_flag, data, result_text, approved_flag):
    saveas_file_path = ''
    try:
        # rename the result file to data['saveas']
        account_id = data["account"]
        dest_folder = calculate_account_folder(account_id)
        result_file_path = os.path.join(dest_folder, data["id"] + '-result.pdf')
        saveas_file = data["saveas"]
        ymd_hm = datetime.now().strftime("%Y%m%d-%H%M")
        # if approved_flag is True, append '-approved' to the saveas_file
        if approved_flag:
            ymd_hm = ymd_hm + '-APPROVED'
        else:
            ymd_hm = ymd_hm + '-REJECTED'

        saveas_file_path = ymd_hm + '-' + saveas_file + '.pdf'
        # replace any spaces in saveas_file with underscores
        saveas_file_path = saveas_file_path.replace(" ", "_")
        saveas_file_path = os.path.join(dest_folder, saveas_file_path)
        if os.path.exists(saveas_file_path):
            os.remove(saveas_file_path)
        shutil.move(result_file_path, saveas_file_path)
    except Exception as e:
        result_text = f"Error: {str(e)}"
        print(result_text)
        continue_flag = False
    return continue_flag, result_text, saveas_file_path

def any_files_to_process() -> bool:
    """
    Check if there are any files to process.
    """
    result = False
    base_path = os.getenv("BASE_PATH", "/tmp")
    # check if there are any files in the base path
    files = []
    try:
        files = os.listdir(base_path)
        files = [f for f in files if f.endswith(".json")]
        if len(files) > 0:
            result = True
    except Exception as e:
        print(f"Error: {str(e)}")
    return result

def get_first_file_to_process() -> str:
    """
    Get the first file to process.
    """
    base_path = os.getenv("BASE_PATH", "/tmp")
    files = []
    try:
        files = os.listdir(base_path)
        files = [f for f in files if f.endswith(".json")]
        if len(files) > 0:
            # get first file without extension
            first_file = [f.split(".")[0] for f in files]
            return first_file
    except Exception as e:
        print(f"Error: {str(e)}")

    return None

def any_files_available():
    rslt = ''
    try:
        # check if there are any files to process
        any_files = any_files_to_process()
        if any_files:
            first_file = get_first_file_to_process()
            if first_file:
                rslt = first_file[0]
            else:
                rslt = ''
        else:
            rslt = 'No files to process'
    except Exception as e:
        rslt = f"Error: {str(e)}"
    return {"message": rslt}

def send_email(filename: str, email_address: str, account: str, state: str, name: str):
    es = EmailSender()
    subject = f'{state} - {name} - {account}'
    short_filename = os.path.basename(filename)
    if state == 'approved':
        body = f'File {short_filename} has been approved for account {account}.' + '\n' + \
            'Please proceed with the next steps.'
    else:
        body = f'File {short_filename} has been rejected for account {account}.' + '\n'

    es.create_message(
        subject=f"Approval Completed - {state} - Account {account}",
        recipients=[email_address],
        plain_body=body,
        html_body=f"<p>{body}</p>",
        attachments=[filename]
    )
    try:
        es.send_email()
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        # Handle the error as needed
        # For example, you might want to log it or retry sending the email

def job():
    rslt = {"message": "Job started"}
    any_files = get_first_file_to_process()
    if any_files is None:
        any_files = []
    if debug_mode:
        print(f"Any files to process: {any_files}")
    #
    # process the first file
    #
    if len(any_files) > 0:
        file_id = any_files[0]
        if debug_mode:
            print(f"Processing file: {file_id}")
        # call the approve function
        rslt = approve(id=file_id)
        if debug_mode:
            print(rslt)
    return rslt

if __name__ == "__main__":
    schedule.every(exec_every_seconds).seconds.do(job)
    seconds = 0
    while True:
        # if debug_mode:
        #     seconds += sleep_time
        #     print(f"{seconds}", end=chr(13))
        schedule.run_pending()
        time.sleep(sleep_time)

