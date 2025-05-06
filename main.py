from fastapi import FastAPI
import uvicorn
import os
import shutil
from dotenv import load_dotenv
import json
from fpdf import FPDF  # Add this import
from PyPDF2 import PdfMerger, PdfWriter  # Add this import
from datetime import datetime

# Load environment variables from .env file
load_dotenv()
app = FastAPI()


@app.get("/")
async def root():
    return {"message": ""}

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

@app.post("/api/exec/{id}")
async def approve(id: str):
    result_text = ''
    continue_flag = True
    file_path = ''
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
            response_file_path = os.path.join(base_path, data["response"])
            response_file = ''
            with open(response_file_path, "r") as f:
                response_file = f.read()

            #
            # now,
            # 1. convert data.response to temp pdf,
            # 2. combine data.file and temp pdf,
            # 3. save to data.result
            #
            temp_pdf_path = os.path.join(base_path, f"{id}_temp.pdf")
            pdf = FPDF()
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
            merger = PdfMerger()
            # Add the original data.file PDF
            original_pdf_path = os.path.join(base_path, data["file"])
            merger.append(original_pdf_path)
            # Add the temp PDF
            merger.append(temp_pdf_path)
            # Save the merged PDF to the result path
            result_pdf_path = os.path.join(base_path, data["result"])
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
        try:
            # move the result file to the account folder
            account_id = data["account"]
            base_path = os.getenv("BASE_PATH", "/tmp")
            result_file_path = os.path.join(base_path, data["result"])
            move_results = move_to_account_folder(result_file_path, account_id)
            if not move_results:
                continue_flag = False
                result_text = f"Error moving file to account folder."
        except Exception as e:
            result_text = f"Error: {str(e)}"
            continue_flag = False

    if continue_flag:
        try:
            # remove temp files for this id
            # for files with name containing id, remove them
            base_path = os.getenv("BASE_PATH", "/tmp")
            temp_files = [f for f in os.listdir(base_path) if f.startswith(id)]
            for temp_file in temp_files:
                temp_file_path = os.path.join(base_path, temp_file)
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
        except Exception as e:
            result_text = f"Error: {str(e)}"
            print(result_text)
            continue_flag = False

    # rename file based on data['saveas']
    if continue_flag:
        try:
            # rename the result file to data['saveas']
            account_id = data["account"]
            dest_folder = calculate_account_folder(account_id)
            result_file_path = os.path.join(dest_folder, data["result"])
            saveas_file = data["saveas"]
            yyyymmdd = datetime.now().strftime("%Y%m%d")
            saveas_file_path = yyyymmdd + '-' + saveas_file + '.pdf'
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

    return {"message": f"{id} -- {result_text}"}


if __name__ == "__main__":
    # Run the app with uvicorn
    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", 8000)))

