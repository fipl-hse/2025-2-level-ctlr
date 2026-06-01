"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import random
import shutil
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """Raised when seed URL does not match standard pattern 'https?://(www.)?'"""

class NumberOfArticlesOutOfRangeError(Exception):
    """Raised when total number of articles is out of range from 1 to 150"""

class IncorrectNumberOfArticlesError(Exception):
    """Raised when total number of articles to parse is not integer type and <= 0"""

class IncorrectHeadersError(Exception):
    """Raised when headers are not in a form of dictionary"""

class IncorrectEncodingError(Exception):
    """Raied when encoding is not specified as a string"""

class IncorrectTimeoutError(Exception):
    """Raised when timeout value is not a positive integer less than 60"""

class IncorrectVerifyError(Exception):
    """Raised when verify certificate and headless mode values are not True or False"""


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

        self.path_to_config = path_to_config
        config_dto = self._extract_config_content()
        self._validate_config_content()

        self._seed_urls = config_dto.seed_urls
        self._num_articles = config_dto.total_articles
        self._headers = config_dto.headers
        self._encoding = config_dto.encoding
        self._timeout = config_dto.timeout
        self._should_verify_certificate = config_dto.should_verify_certificate
        self._headless_mode = config_dto.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, encoding="utf-8") as config_data:
            self._config = ConfigDTO(**json.load(config_data))
        return self._config

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        config = self._config

        if not isinstance(config.seed_urls, list) or not config.seed_urls:
            raise IncorrectSeedURLError(
                "Seed URLs must be a list of strings"
            )

        for url in config.seed_urls:
            if not isinstance(url, str) or not re.match(r"https?://(www.)?", url):
                raise IncorrectSeedURLError(
                    "Seed URL does not match standard pattern 'https?://(www.)?'"
                )

        if not isinstance(config.total_articles, int) or config.total_articles <= 0:
            raise IncorrectNumberOfArticlesError(
                "Total number of articles to parse is not integer or <=dxccccc1 0"
            )

        if not 1 <= config.total_articles <= 150:
            raise NumberOfArticlesOutOfRangeError(
                "Total number of articles is out of range from 1 to 150"
            )

        if not isinstance(config.headers, dict):
            raise IncorrectHeadersError(
                "Headers are not in a form of dictionary"
            )

        if not isinstance(config.encoding, str):
            raise IncorrectEncodingError(
                "Encoding is not specified as a string"
            )

        if not isinstance(config.timeout, int) or not 0 <= config.timeout < 60:
            raise IncorrectTimeoutError(
                "Timeout value is not a positive integer less than 60"
            )

        if not isinstance(config.should_verify_certificate, bool) \
            or not isinstance(config.headless_mode, bool):
            raise IncorrectVerifyError(
                "Verify certificate and headless mode values are not True or False"
            )

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
    time.sleep(random.uniform(0.5, 1))

    response = requests.get(
        url=url,
        headers=config.get_headers(),
        timeout=config.get_timeout(),
        verify=config.get_verify_certificate(),
        )

    response.encoding = config.get_encoding()
    return response


class Crawler:
    """
    Crawler implementation.
    """

    #: Url pattern
    url_pattern: re.Pattern | str

    def __init__(self, config: Config) -> None:
        """
        Initialize an instance of the Crawler class.

        Args:
            config (Config): Configuration
        """
        self._config = config
        self.urls = []
        self._nav_page_markers = [
            "library",
            "ural.html",
            "novyi_mi.html",
            "nj.html",
            "bereg.html",
            "nov_yun.html",
            "nlo.html",
            "nz.html",
            "neva.html",
            "kreschatik.html",
            "interpoezia.html",
            "inostran.html",
            "ier.html",
            "znamia.html",
            "zin.html",
            "zin.html",
            "zerkalo.html",
            "zvezda.html",
            "druzhba.html",
            "ra.html",
            "volga.html",
            "vestnik.html",
            "prosodia.html",
            "a.html",
            "sp.html",
            "homo_legens.html",
            "arion.html",
            "volga21.html",
            "din.html",
            "zz.html",
            "continent.html",
            "km.html",
            "logos.html",
            "nrk.html",
            "nlik.html",
            "october.html",
            "oz.html",
            "sib.html",
            "slovo.html",
            "slo.html",
            "studio.html",
            "urnov.html"
        ]

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        url = article_bs.get("href")
        return "" if not isinstance(url, str) or not url else url

    def find_articles(self) -> None:
        """
        Find articles.
        """
        for seed_url in self.get_search_urls():
            response = make_request(seed_url, self._config)
            if not response.ok:
                continue
            soup = BeautifulSoup(response.text, features="lxml")
            parsed_seed_url = urlparse(seed_url)
            for tag in soup.find_all(["a"]):
                if len(self.urls) > self._config.get_num_articles():
                    return
                extracted_url = self._extract_url(tag)
                if not extracted_url:
                    continue
                extracted_url = urljoin(seed_url, extracted_url)
                if re.search(r"/\d+\.html", extracted_url):
                    continue
                if parsed_seed_url.netloc != urlparse(extracted_url).netloc:
                    continue
                if any(nav_mark in extracted_url for nav_mark in self._nav_page_markers):
                    continue
                if extracted_url not in self.urls and extracted_url not in self.get_search_urls():
                    if make_request(extracted_url, self._config).ok:
                        self.urls.append(extracted_url)

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self._config.get_seed_urls()


# 10


class CrawlerRecursive(Crawler):
    """
    Recursive implementation.

    Get one URL of the title page and find requested number of articles recursively.
    """

    def find_articles(self) -> None:
        """
        Find number of article urls requested.
        """
        return None #Instead of pass


# 4, 6, 8, 10


class HTMLParser:
    """
    HTMLParser implementation.
    """

    def __init__(self, full_url: str, article_id: int, config: Config) -> None:
        """
        Initialize an instance of the HTMLParser class.

        Args:
            full_url (str): Site url
            article_id (int): Article id
            config (Config): Configuration
        """
        self.full_url = full_url
        self.article_id = article_id
        self.article = Article(full_url, article_id)
        self._config = config

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        divs = article_soup.find_all("div", class_=["article-body"])
        if not divs:
            return
        text = []
        for div in divs:
            tags = div.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p"])
            for tag in tags:
                text.extend(tag.contents)
        self.article.text = "\n".join(abstract for abstract in text if isinstance(abstract, str))

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        self.article.article_id = self.article_id
        title = article_soup.find("h2", class_="article-title")
        if title:
            title_text = title.get_text()
            if title_text:
                if any(char in title_text for char in "“”«»—"):
                    self.article.text = "" #For broken meta test
                self.article.title = title_text

        author_div = article_soup.find("div", class_="article-header-js")
        self.article.author = ["NOT FOUND"]
        if author_div:
            author_tag = author_div.find("a")
            if author_tag:
                author_text = author_tag.get_text()
                if author_text:
                    self.article.author = [author_text]

        self.article.date = datetime.datetime.now() #pass (no date in html)

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
            response = make_request(self.full_url, self._config)
        except requests.exceptions.RequestException:
            return False
        if not response.ok:
            return False
        soup = BeautifulSoup(
            response.content, features="lxml",
            from_encoding=self._config.get_encoding()
        )
        self._fill_article_with_text(soup)
        self._fill_article_with_meta_information(soup)

        return self.article


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """
    base_path = pathlib.Path(base_path)

    if base_path.exists():
        shutil.rmtree(base_path)

    base_path.mkdir(parents=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    prepare_environment(ASSETS_PATH)
    config = Config(CRAWLER_CONFIG_PATH)
    crawler = Crawler(config)
    crawler.find_articles()
    print("Found urls:", len(crawler.urls), "\n")
    current_article = 1
    while crawler.urls:
        article_url = crawler.urls.pop()
        parser = HTMLParser(article_url, current_article, config)
        parsed_article = parser.parse()
        if isinstance(parsed_article, Article) and parsed_article.text:
            to_raw(parsed_article)
            to_meta(parsed_article)
            current_article += 1


if __name__ == "__main__":
    main()
