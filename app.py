"""
    Download complete audio books from audioknigi.ru
"""
import contextlib
import json
import re
import os
import sys

import click
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from slugify import slugify


AJAX_ON_SUCCESS = '''
    $(document).ajaxSuccess(function(event, xhr, opt) {
        if (opt.url.indexOf('ajax/bid') !== -1) {
            $('body').html($('<div />', {
                id: 'playlist',
                text: JSON.parse(xhr.responseText).aItems
            }))
        }
    });
'''

INIT_PLAYER = '$(document).audioPlayer({}, 0)'


@contextlib.contextmanager
def open_browser(url):
    """Open a web page with Selenium."""
    profile = webdriver.FirefoxProfile()
    profile.set_preference('permissions.default.image', 2)  # disable images
    browser = webdriver.Firefox(firefox_profile=profile)
    browser.get(url)
    yield browser
    browser.close()


def get_book_id(html):
    """Get the internal book ID."""
    player = re.compile(r'data-global-id="(\d+)\"')
    return player.search(html).group(1)


def scrape_chapters_meta(browser, book_id):
    """Extract chapters metadata from the rendered page."""
    browser.execute_script(AJAX_ON_SUCCESS)
    browser.execute_script(INIT_PLAYER.format(book_id))
    playlist_loaded = EC.presence_of_element_located((By.ID, 'playlist'))
    element = WebDriverWait(browser, 60).until(playlist_loaded)
    return json.loads(element.text)


def get_playlist(audio_book_url):
    """Return a playlist."""
    with open_browser(audio_book_url) as browser:
        book_id = get_book_id(browser.page_source)
        chapters = scrape_chapters_meta(browser, book_id)
    for track in chapters:
        yield track['mp3'], slugify(track['title'])


def download_chapter(url):
    """Download a chapter."""
    return requests.get(url).content


def get_book_title(url):
    """Extract the audiobook name from its URL."""
    return slugify(url.split('/')[-1])


def get_non_blank_path(*dirs):
    """Return the first non-blank directory path."""
    return os.path.abspath(next(filter(bool, dirs)))


def get_or_create_output_dir(dirname, book_title):
    """Create or reuse output directory in a fail-safe manner."""
    path = get_non_blank_path(dirname, book_title, os.getcwd())
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except FileExistsError:
        raise TypeError('"{}" is not a directory.'.format(path))


def contains_files(path):
    """Return True if the directory is not empty."""
    return bool(os.listdir(path))


@click.command()
@click.argument('audio_book_url')
@click.option(
    '-o', '--output-dir', 'output_dir', default=None,
    help=('Download directory. Default: <audio-book-title>')
)
@click.option(
    '-y', '--yes', 'force_overwrite', is_flag=True,
    help='Overwrite existing files without a prompt.'
)
@click.option(
    '-1', '--one-file', 'one_file', is_flag=True,
    help='Merge all book chapters into one file.'
)
def cli(audio_book_url, output_dir, force_overwrite, one_file):
    """Download the complete book."""
    book_title = get_book_title(audio_book_url)
    try:
        path = get_or_create_output_dir(output_dir, book_title)
    except TypeError as exc:
        click.echo(str(exc))
        sys.exit(1)

    if contains_files(path) and not force_overwrite:
        msg = 'The directory "{}" is not empty. Overwite?'.format(path)
        if not click.confirm(msg):
            click.echo('Terminated.')
            sys.exit(0)

    click.echo('Downloading "{}" to "{}"...'.format(audio_book_url, path))

    if one_file:
        output_file = lambda _: open(os.path.join(path, book_title), 'ab')
    else:
        output_file = lambda fname: open(os.path.join(path, fname), 'wb')

    for url, fname in get_playlist(audio_book_url):
        click.echo('Downloading chapter "{}"...'.format(fname))
        with output_file(fname) as outfile:
            outfile.write(download_chapter(url))

    click.echo('All done!\n')


if __name__ == '__main__':
    cli()
