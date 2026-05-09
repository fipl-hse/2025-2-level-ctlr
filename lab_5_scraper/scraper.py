"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import json
import pathlib
import re
import shutil

import requests
from bs4 import BeautifulSoup, Tag

from core_utils.article.article import Article
from core_utils.config_dto import ConfigDTO


class IncorrectSeedURLError(Exception):
    """Seed URL does not match standard pattern."""
    pass

class NumberOfArticlesOutOfRangeError(Exception):
    """Total number of articles is out of range from 1 to 150."""
    pass

class IncorrectNumberOfArticlesError(Exception):
    """Total number of articles to parse is not integer or less than 0."""
    pass

class IncorrectHeadersError(Exception):
    """Headers are not in a form of dictionary."""
    pass

class IncorrectEncodingError(Exception):
    """Encoding must be specified as a string."""
    pass

class IncorrectTimeoutError(Exception):
    """Timeout value must be a positive integer less than 60."""
    pass

class IncorrectVerifyError(Exception):
    """Verify certificate and headless mode values must either be True or False."""
    pass

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
        self._config = self._extract_config_content()
        self._validate_config_content()
        self._seed_urls = self._config.seed_urls
        self._num_articles = self._config.total_articles
        self._headers = self._config.headers
        self._encoding = self._config.encoding
        self._timeout = self._config.timeout
        self._should_verify_certificate = self._config.should_verify_certificate
        self._headless_mode = self._config.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, "r", encoding="utf-8") as file:
            data = json.load(file)
        return ConfigDTO(**data)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        conf = self._config
        standard_pattern = re.compile(r"https?://(www\.)?")
        if not isinstance(conf.seed_urls, list):
            raise IncorrectSeedURLError()
        for url in conf.seed_urls: 
            if not isinstance(url, str) or not standard_pattern.match(url):
                raise IncorrectSeedURLError()
        if not isinstance(conf.total_articles, int):
            raise IncorrectNumberOfArticlesError()
        if conf.total_articles < 1:
            raise IncorrectNumberOfArticlesError()
        if conf.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError()
        if not isinstance(conf.headers, dict):
            raise IncorrectHeadersError()
        if not isinstance(conf.encoding, str):
            raise IncorrectEncodingError()
        if not isinstance(conf.timeout, int) or conf.timeout <= 0 or conf.timeout > 60:
            raise IncorrectTimeoutError()
        if not isinstance(conf.should_verify_certificate, bool):
            raise IncorrectVerifyError()
        if not isinstance(conf.headless_mode, bool):
            raise IncorrectVerifyError()

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
    response = requests.get(
        url,
        headers=config.get_headers(),
        timeout=config.get_timeout(),
        verify=config.get_verify_certificate()
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
        self.config = config
        self.urls = []

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        href = article_bs.get("href", "")
        if not href:
            return ""
        
        if href.startswith("http"):
            return href
        
        if href.startswith("/"):
            return "https://scrapsfromtheloft.com" + href
        
        return "https://scrapsfromtheloft.com/" + href

    def find_articles(self) -> None:
        """
        Find articles.
        """
        for seed_url in self.get_search_urls():
            if len(self.urls) >= self.config.get_num_articles():
                break

            try:
                response = make_request(seed_url, self.config)
            except requests.exceptions.RequestException:
                continue

            if response.status_code != 200:
                continue

            page_soup = BeautifulSoup(response.text, "html.parser")

            all_links = page_soup.find_all("a", href=True)

            for link_tag in all_links:
                if len(self.urls) >= num_articles_needed:
                    break
                
                href = link_tag.get("href", "")
                if not href:
                    continue

                is_transcript = (
                    ("/movie-transcripts/" in href) or 
                    (href.endswith("-transcript")) or
                    ("transcript" in href.lower() and "page" not in href.lower())
                )

                is_excluded = (
                    "page" in href.lower() or
                    "search" in href.lower() or
                    href == "/movie-transcripts/"
                )

                if is_transcript and not is_excluded:
                    full_url = self._extract_url(link_tag)
                    if full_url and full_url not in self.urls:
                        self.urls.append(full_url)
                        print(f"Found article {len(self.urls)}: {full_url}")

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self.config.get_seed_urls()


# 10
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
        self.config = config
        self.article = Article(url=full_url, article_id=article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        h1 = article_soup.find("h1")
        if not h1:
            self.article.text = ""
            return

        content_block = h1.find_parent()
        if content_block:
            paragraphs = content_block.find_all("p")
            if paragraphs:
                self.article.text = "\n".join(
                    p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
                )
            else:
                self.article.text = content_block.get_text(separator="\n", strip=True)
        else:
            self.article.text = ""

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """

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
            response = make_request(self.full_url, self.config)
        except requests.exceptions.RequestException:
            return False

        if response.status_code != 200:
            return False

        article_soup = BeautifulSoup(response.text, "html.parser")
        self._fill_article_with_text(article_soup)
        self._fill_article_with_meta_information(article_soup)

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
    config_path = pathlib.Path("lab_5_scraper/scraper_config.json")
    config = Config(config_path)
    
    prepare_environment("tmp/articles")
    
    crawler = Crawler(config)
    crawler.find_articles()
    
    for article_id, url in enumerate(crawler.urls, start=1):
        parser = HTMLParser(url, article_id, config)
        article = parser.parse()
        if article:
            pass


if __name__ == "__main__":
    main()
