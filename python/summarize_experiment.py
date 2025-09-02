#!/usr/bin/env python

# -*- coding: utf-8 -*-
"""
Summarize the forms of a RSpace notebook into a table. 

Be careful when using this script in other scripts and inputting the user API key rather than fetching it from an environment variable! See the official RSpace API documentation for more information on how to keep your RSpace access secure.

@author: Emil Frang Christiansen (emil.christiansen@ntnu.no)
Created 2025-09-01
"""

import logging
import sys
import os

logger = logging.Logger(__file__)

# Create formatter
#format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
format_string = '%(asctime)s - %(levelname)s - %(message)s'
formatter = logging.Formatter(format_string)

# Set up initial logging
logging.basicConfig(format=format_string, level=logging.ERROR)
logging.captureWarnings(True)

# Create custom logger
logger = logging.getLogger(__file__)
logger.propagate = False

# Create handler
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
logger.setLevel(ch.level)

# Add formatter to handler
ch.setFormatter(formatter)

# Add handler to logger
logger.addHandler(ch)

logger.info(f'This is {__file__} working from {os.getcwd()}:\n{__doc__}')

import argparse
import json
import pandas as pd

from pathlib import Path
from rspace_client.eln import eln
from typing import Union, Any, Iterable, Dict
from tabulate import tabulate
from datetime import date

def get_notebook(notebook_id: str, client: eln.ELNClient) -> Dict:
    """
    Docstring for get_notebook
    
    :param notebook_id: Description
    :type notebook_id: str
    :param client: Description
    :type client: eln.ELNClient
    :return: Description
    :rtype: Dict
    """
    
    notebook = client.get_folder(notebook_id)
    logger.debug(f'Got notebook from ELN:\n{notebook!r}')

    return notebook

def find_forms(notebook_id: str, form_id: str, client:eln.ELNClient) -> Dict:
    """
    Return documents from a specific RSpace ELN notebook that were created with a specific form.

    This function is essentially a wrapper around the `eln.ELNClient.get_documents_advanced_query()` function.
    
    :param notebook: ID of the notebook
    :type notebook: str
    :param form_id: ID of the form used to create the documents.
    :type form_id: str
    :param client: The RSpace ELN client
    :type client: eln.ELNClient
    :return: Description
    :rtype: Dict
    """
    today = date.today().strftime("%Y-%m-%d")

    #Build search query to find the documents/entries related to the notebook.
    advanced_query = json.dumps(
        {"operator": "and", 
        "terms": [
            {"query": f"2020-01-01;{today}", "queryType": "created"},
            {"query": notebook_id, "queryType": "records"},
            {"query": form_id, "queryType": "form"}      
            ]
        }
    )
    logger.debug(f'Using advanced query:\n{advanced_query!r}')

    #Get the documents in the query
    response = client.get_documents_advanced_query(advanced_query)

    #Log some info
    logger.info(f"Found {len(response['documents'])} documents")
    for document in response["documents"]:
        document_response = client.get_document_csv(document["id"])
        logger.debug(f"Answer name: {document['name']}:\n{document_response}\n")

    return response

def form2dict(document_id: str, client:eln.ELNClient, skip_header: bool=True, key_index:int=2, value_index:int=5) -> Dict:
    """
    Return a dictionary of the form fields and their values
    
    :param document_id: The ID of the document to transform to a dictionary
    :type document_id: str
    :param client: The RSpace ELN client to use for access to RSpace.
    :type client: eln.ELNClient
    :param skip_header: Whether to skip the header of the form/document csv representation. Default is True
    :type skip_header: bool
    :param key_index: The index of the document CSV representation to use as the keys in the dictionary. Default is "2" (the name of each form field).
    :type key_index: int
    :param value_index: The index of the document CSV representation to use as the values in the dictionary. Default is "5" (the value of each form field).
    :type value_index: int
    :return: The form field names and values in a dictionary.
    :rtype: dict
    """

    form_content = client.get_document_csv(document_id).splitlines()
    #The csv representation of a document is a comma-separated string containing information about each form field of the document separated by newlines. Remember, all documents in RSpace are, in practice, forms!
    #Each line in the `form_content` string above contains at least ["ID", "GlobalID", "name", "type", "lastModified", "content"]
    logger.debug(f'Got form content from docment ID {document_id}:\n{form_content!s}')

    #Create a dictionary with the name (default 2nd column) of each field as keys and the value (default 5th column) as values:
    if skip_header:
        logger.debug(f'Skipping header row of form: "{form_content[0]!s}"')
        form_content = form_content[1:] #Skip the 0th line that contains the "headers" in the form:
    
    content = {line.split(',')[key_index]: line.split(',')[value_index] for line in form_content}
    logger.debug(f'Created dictionary from form:\n{content!r}')

    return content

def notebook2dataframe(notebook_id: str, form_id: str, client:eln.ELNClient, *args, sort:Union[None, str]=None, **kwargs) -> pd.DataFrame:
    """
    Create a pandas dataframe from RSpace documents created using the same form.
    
    :param notebook_id: The ID of the notebook that contains the documents to be summarized
    :type documents: str
    :param form_id: The ID of the form used to create the documents to be summarized.
    :type form_id: str
    :param client: The RSpace eln client.
    :type client: eln.ELNClient
    :param sort: Form field name to use when sorting the summary. Default is None which will perform no sorting.
    :type sort: Union[None, str]
    :param args: Optional positional arguments passed to `form2dict()`
    :param kwargs: Optional keyword arguments passed to `form2dict()`
    :return: Summary data frame
    :rtype: pd.DataFrame
    """
    documents = find_forms(notebook_id=notebook_id, form_id=form_id, client=client)
    form_data = []
    for document in documents['documents']:
        logger.debug(f'{document!s}')
        logger.debug(f'Extracting form data from document with ID {document["id"]}')
        try:
            form_data.append(form2dict(document["id"], client=client, *args, **kwargs))
        except Exception as e:
            logger.error(f'Could not add data from document with ID {document["id"]}:\n{document}')
            raise e
    summary = pd.DataFrame(form_data)

    if sort is not None:
        try:
            summary.sort_values(sort)
        except Exception as e:
            logger.error(f'Could not sort dataframe with columns {summary.columns!r} due to error {e}')
    logger.debug(f'Created summary of {len(documents)} documents: \n{summary!r}')
    return summary

def create_summary_text(summary:pd.DataFrame, file_id:Union[None, str], *args, **kwargs) -> str:
    """
    Create a summary text to put in a document on RSpace.
    
    :param summary: The summary dataframe
    :type summary: pd.DataFrame
    :param file_id: The RSpace file ID to the uploaded summary file. If None, no link to files will be created.
    :type file_id: Union[None, str]
    :param args: Optional positional arguments passed to `tabulate()`
    :param kwargs: Optional keyword arguments passed to `tabulate()`. The default `tablefmt` is overwritten to be "html".
    :return: Summary text.
    :rtype: str
    """
    kwargs['tablefmt'] = kwargs.get('tablefmt', 'html') #Set default table format to html.

    text = f"<h1>Summary table</h1>\n" #Header of document

    text += tabulate(summary, *args, headers=summary.columns, **kwargs) #Tabulate the summary

    if file_id is None:
        text += f"\n\nNo ID to summary file on RSpace is provided"
    else:
        text += f"\n\nSummary file: <fileId={file_id}>" #Link to the uploaded file.

    logger.debug(f'Created text to put on RSpace:\n<START>\n{text}\n<END>')

    return text

def upload(notebook_id: str, summary:pd.DataFrame, client:eln.ELNClient, *args, no_upload:bool=False, **kwargs):

    #Save summary to file
    notebook = get_notebook(notebook_id, client=client)
    summary_path = Path(f"{notebook['name']}_summary.csv")
    summary.to_csv(summary_path)
    logger.info(f'Saved summary to file: "{summary_path.absolute()}"')

    if no_upload:
        logger.info(f'No uploads requested. Skipping upload of summary file.')
        file_id = None
    else:
        logger.info(f'Uploading files to RSpace')
        with summary_path.open('r') as f:
            file_upload = client.upload_file(f)
            file_id = file_upload['id']
            logger.info(f"Uploaded file with ID {file_id}")
    
    text = create_summary_text(summary=summary, *args, file_id=file_id, **kwargs)
    logger.debug(f'Summary text:\n<START>\n{text!s}\n<END>')

    if no_upload:
        logger.info(f'No uploads requested. Skipping creation of summary document.')
    else:
        logger.info(f'Creating RSpace summary document')
        summary_document = client.create_document(summary_path.stem, parent_folder_id=notebook_id, fields=[{"content": text}])
        logger.info(f"Created summary document with ID {summary_document['id']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('notebook_id', type=str, help='Notebook ID')
    parser.add_argument('form_id', type=str, help='ID of the form used to create documents to be summarized')
    parser.add_argument('--rspace_url', type=str, default = r"https://rspace.ntnu.no/", help='URL to ELN')
    parser.add_argument('--api_key', type=str, default=None, help='User API key to access ELN. Be careful how you use this, as the key should be treated the same as your password! If not provided, it will look for it in an environment variable called "RSPACE_API_KEY". See the official RSpace API documentation on how to set the API key in an environment variable and keep it secure.')
    parser.add_argument('--sort', type=str, default=None, help=f'Form field name to use to sort the summary table.')
    parser.add_argument('--skip_header', action='store_true', help=f'Whether to skip the header of the form CSV representation or not.')
    parser.add_argument('--key_index', type=int, default=2, help=f'The index of the form CSV representation to use as keys (column names) in the summary. Default is 2 and will use the names of the form fields.')
    parser.add_argument('--value_index', type=int, default=5, help=f'The index of the form CSV representation to use as the values in the summary. Default is 5 which will use the values in each form field.')
    parser.add_argument('--no_upload', action='store_true', help=f"Don't upload summary file and summary document to RSpace. Used for debugging purposes.")
    parser.add_argument('-v', '--verbosity', action='count', default=0, help='Increase the verbosity')
    
    args = parser.parse_args()

    if args.verbosity == 0:
        ch.setLevel(logging.WARNING)
    elif args.verbosity == 1:
        ch.setLevel(logging.INFO)
    else:
        ch.setLevel(logging.DEBUG)
    logger.setLevel(ch.level)

    logger.debug(f"Got input arguments: {args}")

    if args.api_key is None:
        logger.debug('Getting API key from environment variable')
        api_key = os.getenv("RSPACE_API_KEY")
    else:
        api_key = args.api_key

    client = eln.ELNClient(args.rspace_url, api_key)
    logger.info(f"Connected to ELN client: {client}")

    try:
        summary = notebook2dataframe(args.notebook_id, form_id = args.form_id, client=client, sort=args.sort, key_index=args.key_index, value_index=args.value_index, skip_header=args.skip_header)
    except Exception as e:
        logger.error(f'Could not create summary of documents created with form "{args.form_id}" in notebook "{args.notebook_id}" due to error {e}')
        raise e
    else:
        upload(args.notebook_id, summary, client=client, no_upload=args.no_upload)
    
    logger.info(f'Finished summarization script.')