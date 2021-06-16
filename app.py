from flask import Flask, render_template, redirect, url_for, send_from_directory, abort, session, request
from flask_wtf import FlaskForm
from flask_paginate import Pagination, get_page_args
from wtforms.fields import StringField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp
from scrapy import signals
from scrapy.crawler import CrawlerRunner
from scrapy.signalmanager import dispatcher
from .scraper import ShopeeSpider, query_input
from datetime import timedelta
import pandas as pd
import urllib.parse
import logging
import re
import datetime
import pytz
import os
import secrets
import json
import crochet

crochet.setup()  # initialize crochet

# secret_key = secrets.token_urlsafe(16)
session_val = secrets.token_urlsafe(6)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'simpleshopeeshopproductsscraper'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['OUTPUT_DIR'] = 'output/'
# crawl_runner = CrawlerRunner()  # requires the Twisted reactor to run
output_data = []  # store output
scrape_in_progress = False
scrape_complete = False
input_query = False  # set True after input query
start_url = ''
filepath = ''


class InputProductForm(FlaskForm):
    product_query = StringField('Shop Label:', validators=[DataRequired(),
                                                           Length(min=25, max=100,
                                                                  message='Please input Shop Url, length: 25-100 Characters'),
                                                           ])
    submit = SubmitField('Scrape')


@app.route('/', methods=['GET', 'POST'])
def home():
    session['visitor'] = session_val
    title = 'Shopi Scraper'
    form = InputProductForm()

    if form.validate_on_submit():
        global start_url
        start_url = form.product_query.data
        # keyword = urllib.parse.quote(kw, safe='')

        # sanitize form query to filename
        # kw_x = re.sub(r"[^\w]+", "_", kw)
        # kw_y = re.sub(r"[_]+", " ", kw_x).strip()
        filename_kw = query_input(start_url)

        # add datetime to filename
        global filepath
        jkt_tz = datetime.datetime.now(pytz.timezone('Asia/Jakarta')).date()
        filepath = 'output/output-{}-{}.csv'.format(jkt_tz, filename_kw)
        # filepath = 'output/output-{}-{}.json'.format(jkt_tz, filename_kw)

        # global input_query
        # input_query = True

        global scrape_in_progress
        scrape_in_progress = True

        global scrape_complete
        scrape_complete = False

        global output_data
        output_data = []

        # Remove existing output file
        # if os.path.exists("output/outputjson.json"):
        #     os.remove("output/outputjson.json")

        return redirect(url_for('scrape', que=filename_kw))  # Passing to the Scrape function

    else:
        return render_template('index.html', title=title, form=form)


@app.route('/scrape/<que>')
def scrape(que):
    title = 'Scraping Progress'
    query = que.replace('-', ' ')
    # Process scrape data
    global scrape_in_progress
    global scrape_complete
    # global input_query

    if scrape_in_progress and not scrape_complete:
        # scrape_in_progress = True
        global output_data

        # log
        scrape_logging()

        # start the crawler and execute a callback when complete
        scrape_with_crochet(start_url, output_data, filepath)
        # input_query = False  # set False after scraping in progress
        return render_template('scrape-progress.html', title=title, query=query)
    elif scrape_complete:
        return render_template('scrape-complete.html', title=title, query=query)
    else:
        return render_template('scrape-nojob.html', title=title)


def get_files(files_, offset=0, per_page=10):
    return files_[offset: offset + per_page]


@app.route('/files')
def file_listing():
    title = 'File List'

    try:
        # Show directory contents
        list_files = os.listdir(app.config["OUTPUT_DIR"])

        # Sorted by time
        full_list = [os.path.join(app.config["OUTPUT_DIR"], i) for i in list_files]
        time_sorted_list = sorted(full_list, key=os.path.getmtime, reverse=True)
        time_sorted_fname = [os.path.basename(f) for f in time_sorted_list]

        page, per_page, offset = get_page_args(page_parameter='page',
                                               per_page_parameter='per_page')

        # re-assign per_page to change value (default 10)
        per_page = 10
        total = len(list_files)
        pagination_files = get_files(time_sorted_fname, offset=offset, per_page=per_page)
        pagination = Pagination(page=page, per_page=per_page, total=total,
                                css_framework='bootstrap4')
        return render_template('files.html',
                               title=title,
                               files=pagination_files,
                               page=page,
                               per_page=per_page,
                               pagination=pagination,
                               )
    except FileNotFoundError:
        empty_list = 'List is empty.'
        return render_template('files.html', title=title, message=empty_list)


# OUTPUT CSV
@app.route("/files/<path:output_filename>")
def files(output_filename):
    try:
        title = 'View File'
        filename = os.path.join(app.config["OUTPUT_DIR"], output_filename)
        df = pd.read_csv(filename)
        df.index += 1
        return render_template('result.html', title=title, data=df.to_html(classes="table table-hover"), output_filename=output_filename, titles=df.columns.values)
    except FileNotFoundError:
        abort(404)


# OUTPUT JSON
# @app.route("/files/<path:output_filename>")
# def files(output_filename):
#     try:
#         title = 'View File'
#         filename = os.path.join(app.config["OUTPUT_DIR"], output_filename)
#         with open(filename) as json_file:
#             try:
#                 file_json = json.load(json_file)
#                 output_json = json.dumps(file_json, indent=4, separators=(',', ': '))
#             except JSONDecodeError:
#                 empty_file = 'File is empty.'
#                 return render_template('scrape-error.html', title=title, message=empty_file)
#         return render_template('result.html', title=title, output_json=output_json, output_filename=output_filename)
#     except FileNotFoundError:
#         abort(404)


@app.route("/download/<path:output_filename>")
def download(output_filename):
    try:
        return send_from_directory(app.config['OUTPUT_DIR'], path=output_filename, as_attachment=True)
    except FileNotFoundError:
        abort(404)


@app.route('/about')
def about():
    title = 'About'
    return render_template('about.html', title=title)


@app.errorhandler(404)
def page_not_found(e):
    # note that we set the 404 status explicitly
    return render_template('404.html'), 404


@crochet.run_in_reactor
def scrape_with_crochet(starturl_query, output, output_filepath):
    dispatcher.connect(_crawler_result, signal=signals.item_scraped)
    crawl_runner = CrawlerRunner(settings={
        'DEFAULT_REQUEST_HEADERS': {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36',
            'Referer': 'https://shopee.co.id/',
        },
        'DOWNLOAD_DELAY': 2,
        "FEEDS": {
            output_filepath: {"format": "csv"},
        },
    })

    eventual = crawl_runner.crawl(ShopeeSpider, url_query=starturl_query, output_data=output)
    eventual.addCallback(finished_scrape)


# This will append the data to the output data list.
def _crawler_result(item, response, spider):
    output_data.append(dict(item))


def finished_scrape(null):
    """
    """
    global scrape_complete
    scrape_complete = True

    global scrape_in_progress
    scrape_in_progress = False


def scrape_logging():
    # configure_logging(install_root_handler=False)
    logging.basicConfig(
        filename='log/scrapinglog.txt',
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        level=logging.WARNING
    )


if __name__ == '__main__':
    # app.run(host='0.0.0.0')
    app.run(debug=True)
