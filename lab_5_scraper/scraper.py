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
from core_utils.article.io import to_raw, to_meta

class IncorrectSeedURLError(Exception):
    pass

class NumberOfArticlesOutOfRangeError(Exception):
    pass

class IncorrectNumberOfArticlesError(Exception):
    pass

class IncorrectHeadersError(Exception):
    pass

class IncorrectEncodingError(Exception):
    pass

class IncorrectTimeoutError(Exception):
    pass

class IncorrectVerifyError(Exception):
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
        self.config_content = self._extract_config_content()
        self._validate_config_content()

        self._seed_urls = self.config_content.seed_urls
        self._num_articles = self.config_content.total_articles
        self._headers = self.config_content.headers
        self._encoding = self.config_content.encoding
        self._timeout = self.config_content.timeout
        self._should_verify_certificate = self.config_content.should_verify_certificate
        self._headless_mode = self.config_content.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, 'r', encoding='utf-8') as f:
            config_data =  json.load(f)
        return ConfigDTO(**config_data)

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """

        if not isinstance(self.config_content.seed_urls, list):
            raise IncorrectSeedURLError('seed URL does not match standard pattern "https?://(www.)?"')
        for url in self.config_content.seed_urls:
            if not isinstance(url, str) or not re.match(r"https?://(www\.)?", url):
                raise IncorrectSeedURLError ('seed URL does not match standard pattern "https?://(www.)?"')
            
        if not isinstance(self.config_content.total_articles, int) or isinstance(self.config_content.total_articles, bool) or self.config_content.total_articles < 1:
            raise IncorrectNumberOfArticlesError("total number of articles to parse is not integer or less than 0")

        if self.config_content.total_articles > 150:
            raise NumberOfArticlesOutOfRangeError("total number of articles is out of range from 1 to 150")
        
        if not isinstance(self.config_content.headers, dict):
            raise IncorrectHeadersError("headers are not in a form of dictionary")
        
        if not isinstance(self.config_content.encoding, str):
            raise IncorrectEncodingError("encoding must be specified as a string")
        
        if not isinstance(self.config_content.timeout, int) or self.config_content.timeout < 0 or self.config_content.timeout > 60:
            raise IncorrectTimeoutError("timeout value must be a positive integer less than 60")
        
        if not isinstance(self.config_content.should_verify_certificate, bool) or not isinstance(self.config_content.headless_mode, bool):
            raise IncorrectVerifyError("verify certificate and headless mode values must either be True or False")
        

    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """
        return self.config_content.seed_urls

    def get_num_articles(self) -> int:
        """
        Retrieve total number of articles to scrape.

        Returns:
            int: Total number of articles to scrape
        """
        return self.config_content.total_articles

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting.

        Returns:
            dict[str, str]: Headers
        """
        return self.config_content.headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
        """
        return self.config_content.encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        return self.config_content.timeout

    def get_verify_certificate(self) -> bool:
        """
        Retrieve whether to verify certificate.

        Returns:
            bool: Whether to verify certificate or not
        """
        return self.config_content.should_verify_certificate

    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode.

        Returns:
            bool: Whether to use headless mode or not
        """
        return self.config_content.headless_mode


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
        self.config = config
        self.urls: list[str] = []

    def _extract_url(self, article_bs: Tag) -> str:
        """
        Find and retrieve url from HTML.

        Args:
            article_bs (bs4.Tag): Tag instance

        Returns:
            str: Url from HTML
        """
        href = article_bs.get("href", "")
        if not isinstance(href, str):
            return ''
        if not re.search(r"/press/art_\d+/", href):
            return ""
        if href.startswith('http'):
            return href
        return "https://www.newdrama.ru" + href


    def find_articles(self) -> None:
        """
        Find articles.
        """
        urls_to_visit = list(self.get_search_urls())
        visited = set()

        while urls_to_visit and len(self.urls) < self.config.get_num_articles():
            current_url = urls_to_visit.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)

            try:
                response = make_request(current_url, self.config)
                if response.status_code != 200:
                    continue
                soup = BeautifulSoup(response.text, "html.parser")

                for tag in soup.find_all("a", href=True):
                    if len(self.urls) >= self.config.get_num_articles():
                        break
                    url = self._extract_url(tag)
                    if url and url not in self.urls:
                        self.urls.append(url)

                for tag in soup.find_all("a", href=True):
                    href = tag.get("href", "")
                    if not isinstance(href, str):
                        continue
                    if re.search(r"/press/\d+/?$", href):
                        if href.startswith("http"):
                            next_url = href
                        else:
                            next_url = "https://www.newdrama.ru" + href
                        if next_url not in visited:
                            urls_to_visit.append(next_url)

            except requests.exceptions.RequestException:
                continue

    def get_search_urls(self) -> list:
        """
        Get seed_urls param.

        Returns:
            list: seed_urls param
        """
        return self.config.get_seed_urls()


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
        paragraphs = article_soup.find_all("p")
        texts = []
        for p in paragraphs:
            text = p.get_text(separator=" ", strip=True)
            if text:
                texts.append(text)
        self.article.text = "\n".join(texts)

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title_tag = article_soup.find("b")
        if title_tag:
            self.article.title = title_tag.get_text(separator=" ", strip=True)
        else:
            self.article.title = "NOT FOUND"

        italic_tag = article_soup.find("i")
        if italic_tag:
            raw = italic_tag.get_text(strip=True)
            match = re.match(r"^(.*?)\s*\((.+?)\)\s*$", raw)
            if match:
                author = match.group(1).strip()
                self.article.author = [author] if author else ["NOT FOUND"]
                date_str = match.group(2).strip()
                self.article.date = self.unify_date_format(date_str)
            else:
                self.article.author = [raw] if raw else ["NOT FOUND"]
        else:
            self.article.author = ["NOT FOUND"]

        url_match = re.search(r"newdrama\.ru/(\w+)/", self.full_url)
        if url_match:
            self.article.topics = [url_match.group(1)]
        else:
            self.article.topics = []

        self.article.url = self.full_url


    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """
        formats = ["%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"]
        for fmt in formats:
            try:
                return datetime.datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return datetime.datetime(2000, 1, 1)

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        try:
            response = make_request(self.full_url, self.config)
            if response.status_code != 200:
                return False
        except requests.exceptions.RequestException:
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
    base_path.mkdir(parents=True, exist_ok=True)



def main() -> None:
    """
    Entrypoint for scraper module.
    """
    config = Config(path_to_config=pathlib.Path("lab_5_scraper/scraper_config.json"))
    prepare_environment(base_path=pathlib.Path("tmp/articles"))

    crawler = Crawler(config=config)
    crawler.find_articles()

    for article_id, url in enumerate(crawler.urls, start=1):
        parser = HTMLParser(full_url=url, article_id=article_id, config=config)
        article = parser.parse()
        if isinstance(article, Article):
            to_raw(article)
            to_meta(article)


if __name__ == "__main__":
    main()
