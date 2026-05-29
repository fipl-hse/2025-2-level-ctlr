"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import re
from io import BytesIO

import requests
from bs4 import BeautifulSoup, Tag
from docx import Document

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """Exception raised when seed URL does not match standard pattern \"https?://(www.)?\""""

class NumberOfArticlesOutOfRangeError(Exception):
    """Exception raised when total number of articles is out of range from 1 to 150"""

class IncorrectNumberOfArticlesError(Exception):
    """Exception raised when total number of articles to parse is not integer or less than 0"""

class IncorrectHeadersError(Exception):
    """Exception raised when headers are not in a form of dictionary"""

class IncorrectEncodingError(Exception):
    """Exception raised when encoding is not specified as a string"""

class IncorrectTimeoutError(Exception):
    """Exception raised when timeout value is not a positive integer less than 60"""

class IncorrectVerifyError(Exception):
    """Exception raised when certificate or headless mode values must are not either True or False"""

class Config:
    """
    Class for unpacking and validating configurations.
    """

    def __init__(self, path_to_config: pathlib.Path) -> None:
        """
        Initialize an instance of the Config class.

        Args:
            path_to_config (pathlib.Path): Path to configuration.
        """
        
        self.path_to_config : pathlib.Path = path_to_config
        self._seed_urls: list[str] = []
        self._num_articles: int = 0
        self._headers: dict[str, str] = {}
        self._encoding: str = ""
        self._timeout: int = 0
        self._should_verify_certificate: bool = False
        self._headless_mode: bool = False
        
        self._validate_config_content()

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """

        with open(self.path_to_config, encoding="utf-8") as config_file:
            config_data = json.load(config_file)
            return ConfigDTO(**config_data)


    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
                
        config_values = self._extract_config_content()


        if not isinstance(config_values.seed_urls, list):
            raise IncorrectSeedURLError()

        for url in config_values.seed_urls:
            if not re.match("https?://(www.)?", url):
                raise IncorrectSeedURLError()

        if not isinstance(config_values.total_articles, int) or isinstance(config_values.total_articles, bool):
            raise IncorrectNumberOfArticlesError()
        
        if config_values.total_articles < 0:
            raise IncorrectNumberOfArticlesError()

        if not (1 <= config_values.total_articles < 150):
            raise NumberOfArticlesOutOfRangeError()
    
        if not isinstance(config_values.headers, dict):
            raise IncorrectHeadersError()

        if not isinstance(config_values.encoding, str):
            raise IncorrectEncodingError()
    
        if not isinstance(config_values.timeout, int) or isinstance(config_values.timeout, bool):
            raise IncorrectTimeoutError()
    
        if config_values.timeout < 0 or config_values.timeout > 60:
            raise IncorrectTimeoutError()
    
        if not isinstance(config_values.headless_mode, bool) or not isinstance(config_values.should_verify_certificate, bool):
            raise IncorrectVerifyError()

        self._seed_urls = config_values.seed_urls
        self._num_articles = config_values.total_articles
        self._headers: dict[str, str] = config_values.headers
        self._encoding: str = config_values.encoding
        self._timeout: int = config_values.timeout
        self._should_verify_certificate: bool = config_values.should_verify_certificate
        self._headless_mode: bool = config_values.headless_mode
        


    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """

        return self._seed_urls

    def get_num_articles(self) -> int:
        """
        Retrieve total number of articles to scrape.

        Returns:
            int: Total number of articles to scrape
        """

        return self._num_articles

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting.

        Returns:
            dict[str, str]: Headers
        """

        return self._headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
        """

        return self._encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        
        return self._timeout

    def get_verify_certificate(self) -> bool:
        """
        Retrieve whether to verify certificate.

        Returns:
            bool: Whether to verify certificate or not
        """

        return self._should_verify_certificate

    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode.

        Returns:
            bool: Whether to use headless mode or not
        """

        return self._headless_mode


def make_request(url: str, config: Config) -> requests.models.Response:
    """
    Deliver a response from a request with given configuration.

    Args:
        url (str): Site url
        config (Config): Configuration

    Returns:
        requests.models.Response: A response from a request
    """

    response = requests.get(url, headers=config.get_headers(), timeout=config.get_timeout(), 
                            verify=config.get_verify_certificate(), allow_redirects=True)
    response.encoding = config.get_encoding()
    return response

class Crawler:
    """
    Crawler implementation.
    """

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the Crawler class.

        Args:
            config (Config): Configuration
        """

        self._config : Config = config
        self.urls : list[str] = []
        self._page_counts : list[int] = []

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: url from HTML
        """

        relative_article_id = self._get_relative_article_id(len(self.urls))
        page_number = article_bs.find(class_="pager-current").text

        return "https://theatre-library.ru/" + "?page=" + str(page_number) + "article=" + str(relative_article_id)
        

    def find_articles(self) -> None:
        """
        Find articles.
        """

        for search_url_index, article_url in enumerate(self.get_search_urls()):
                
                try:
                    response = make_request(article_url, self._config)
                except requests.RequestException:
                    print(f"Failed to load page {article_url}")
                    continue

                if not response.ok:
                    continue

                soup = BeautifulSoup(response.text, features="lxml")

                article_count = 0

                for article_bs in soup.find_all(class_="th_d1"):
                    if len(self.urls) == self._config.get_num_articles():
                        break
                    
                    self.urls.append(self._extract_url(soup))

                    article_count += 1
                
                self._page_counts.append(article_count)
        
    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """

        return self._config.get_seed_urls()

    def _get_relative_article_id(self, article_id : int) -> int:

        """
        Get number of the article relative to its page

        Args:
            article_id (int): id of the article

        Returns:
            str: url from HTML
        """


        article_count = 0

        for seed_id, pcount in enumerate(self._page_counts):
            if article_count + pcount >= article_id:
                print(article_id, article_count)
                break
            article_count += pcount
        
        return article_id - article_count


# 10


class CrawlerRecursive(Crawler):
    """
    Recursive implementation.

    Get one URL of the title page and find requested number of articles recursively.
    """

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the CrawlerRecursive class.

        Args:
            config (Config): Configuration
        """

    def find_articles(self) -> None:
        """
        Find number of article urls requested.
        """


# 4, 6, 8, 10


class HTMLParser:
    """
    HTMLParser implementation.
    """

    config : Config
    article_id : int
    full_url : str

    def __init__(self, full_url: str, article_id: int, config: Config) -> None:
        """
        Initialize an instance of the HTMLParser class.

        Args:
            full_url (str): Site url
            article_id (int): Article id
            config (Config): Configuration
        """

        self.config = config
        self.full_url = full_url
        self.article_id = article_id
        self.article = Article(full_url, article_id)



    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """

        document_bs = article_soup.find("a")["href"]
        document_url = "https://theatre-library.ru" + document_bs
        
        try:
            response = make_request(document_url, self.config)
        except requests.RequestException:
            print(f"Failed to download document from {document_url}")
            return

        if not response.ok:
            print(f"Failed to download document from {document_url}")
            return

        try:
            doc = Document(BytesIO(response.content))
        except:
            print(f"Failed to extract {document_url} as .docx file")
            return


        parser = WordParser(doc, self.article)

        article_text = parser.parse()

        self.article.text = article_text


    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """

        primary_meta = article_soup.find_all(class_="uline")

        self.article.title = primary_meta[0].text.strip("«»")

        if len(primary_meta) > 1:
            self.article.author = [author.text for author in primary_meta[1:]]
        else:
            self.article.author = "NOT FOUND"

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """

        try:
            response = make_request(self.article.url, self.config)
        except requests.RequestException:
            return False

        if not response.ok:
            return False

        article_bs = BeautifulSoup(response.text, features="lxml")

        relative_article_id = int(self.article.url[self.article.url.rfind("=")+1:])

        print(self.article_url)

        article_bs = article_bs.find_all(class_="th_d1")[relative_article_id]

        self._fill_article_with_meta_information(article_bs)

        self._fill_article_with_text(article_bs)

        if self.article.text == "":
            return False

        return self.article

def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """

    if base_path.exists():
        for stored_file in base_path.iterdir():
            stored_file.unlink()
        base_path.rmdir()
    
    base_path.mkdir(parents=True)

class WordParser:

    """
    Parses text from a docx file
    """

    _doc : Document
    article : Article

    def __init__(self, doc : Document, article : Article) -> None:
        """
        Initialize an instance of the WordParser class.

        Args:
            doc (Document): Document
            article : Article
        """

        self._doc = doc
        self.article = article

    def parse(self) -> str:

        text = ""

        for paragraph in self._doc.paragraphs:
            text += paragraph.text
            text += "\n"

        return text


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    
    configuration = Config(path_to_config=CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)
    crawler = Crawler(config=configuration)
    crawler.find_articles()

    skipped_articles = 0

    for article_id, full_url in enumerate(crawler.urls):

        html_parser = HTMLParser(full_url=full_url, article_id=article_id+1-skipped_articles, config=configuration)
        article = html_parser.parse()

        if article == False:
            print(f"Failed to parse article {article_id+1-skipped_articles} ({article_id+1})")
            skipped_articles += 1
            continue
        
        to_raw(article)
        to_meta(article)
        

if __name__ == "__main__":
    main()
