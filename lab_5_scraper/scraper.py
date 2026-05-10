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
from core_utils.article.io import to_meta, to_raw
from core_utils.config_dto import ConfigDTO
from core_utils.constants import ASSETS_PATH, CRAWLER_CONFIG_PATH


class IncorrectSeedURLError(Exception):
    """
    Seed URL does not match standard pattern "https?://(www.)?".
    """

class NumberOfArticlesOutOfRangeError(Exception):
    """
    Total number of articles is out of range from 1 to 150.
    """

class IncorrectNumberOfArticlesError(Exception):
    """
    Total number of articles to parse is not integer or less than 0.
    """

class IncorrectHeadersError(Exception):
    """
    Headers are not in a form of dictionary.
    """

class IncorrectEncodingError(Exception):
    """
    Encoding must be specified as a string.
    """

class IncorrectTimeoutError(Exception):
    """
    Timeout value must be a positive integer less than 60.
    """

class IncorrectVerifyError(Exception):
    """
    Verify certificate and headless mode values must either be True or False.
    """

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
        self.config_dto = self._extract_config_content()
        self._validate_config_content()
        self._seed_urls = self.config_dto.seed_urls
        self._num_articles = self.config_dto.total_articles
        self._headers = self.config_dto.headers
        self._encoding = self.config_dto.encoding
        self._timeout = self.config_dto.timeout
        self._should_verify_certificate = self.config_dto.should_verify_certificate

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        return ConfigDTO(
            seed_urls=config_data.get('seed_urls', []),
            headers=config_data.get('headers', {}),
            total_articles_to_find_and_parse=config_data.get('total_articles_to_find_and_parse', 0),
            encoding=config_data.get('encoding', 'utf-8'),
            timeout=config_data.get('timeout', 10),
            should_verify_certificate=config_data.get('should_verify_certificate', True),
            headless_mode=config_data.get('headless_mode', True)
        )

    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        if not isinstance(self.config_dto.seed_urls, list):
            raise IncorrectSeedURLError("Seed URLs must be a list")
        for url in self.config_dto.seed_urls:
            if not isinstance(url, str) or not re.match(r'^https?://(www\.)?', url):
                raise IncorrectSeedURLError(f"Invalid seed URL: {url}")
        if not isinstance(self.config_dto.total_articles, int):
            raise IncorrectNumberOfArticlesError("Number of articles must be a positive integer")
        num = self.config_dto.total_articles
        if num <= 0:
            raise IncorrectNumberOfArticlesError("Number of articles must be a positive integer")
        if num > 150:
            raise NumberOfArticlesOutOfRangeError("Number of articles must be between 1 and 150")
        if not isinstance(self.config_dto.headers, dict):
            raise IncorrectHeadersError("Headers must be a dictionary")
        if not isinstance(self.config_dto.encoding, str):
            raise IncorrectEncodingError("Encoding must be a string")
        timeout = self.config_dto.timeout
        if not isinstance(timeout, int) or timeout <= 0 or timeout > 60:
            raise IncorrectTimeoutError("Timeout must be a positive integer less than 60")
        if not isinstance(self.config_dto.should_verify_certificate, bool):
            raise IncorrectVerifyError("Verify certificate must be a boolean")
        if not isinstance(self.config_dto.headless_mode, bool):
            raise IncorrectVerifyError("Headless mode must be either True or False")

    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """
        return self.config_dto.seed_urls

    def get_num_articles(self) -> int:
        """
        Retrieve total number of articles to scrape.

        Returns:
            int: Total number of articles to scrape
        """
        return self.config_dto.total_articles

    def get_headers(self) -> dict[str, str]:
        """
        Retrieve headers to use during requesting.

        Returns:
            dict[str, str]: Headers
        """
        return self.config_dto.headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
        """
        return self.config_dto.encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        return self.config_dto.timeout

    def get_verify_certificate(self) -> bool:
        """
        Retrieve whether to verify certificate.

        Returns:
            bool: Whether to verify certificate or not
        """
        return self.config_dto.should_verify_certificate

    def get_headless_mode(self) -> bool:
        """
        Retrieve whether to use headless mode.

        Returns:
            bool: Whether to use headless mode or not
        """
        return self.config_dto.headless_mode


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
        href = article_bs.get('href', '')
        if isinstance(href, str) and 'news.php?id=' in href:
            if href.startswith('http'):
                return href
            clean_href = href.lstrip('/')
            return f"https://fabulae.ru/{clean_href}"
        return ""

    def find_articles(self) -> None:
        """
        Find articles.
        """
        needed = self.config.get_num_articles()
        for seed_url in self.config.get_seed_urls():
            if len(self.urls) >= needed:
                break
            response = make_request(seed_url, self.config)
            if not response or response.status_code != 200:
                continue
            soup = BeautifulSoup(response.content, 'html.parser')
            all_links = soup.find_all('a')
            for link in all_links:
                if len(self.urls) >= needed:
                    break
                article_url = self._extract_url(link)
                if article_url and article_url not in self.urls:
                    self.urls.append(article_url)
    def get_search_urls(self) -> list:
        """
        Get seed_urls param.
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
        super().__init__(config)
        self.visited_urls = set()

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
        self.article = Article(full_url, article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        title_tag = article_soup.find('h1')
        if not title_tag:
            title_tag = article_soup.find('h2')
        if title_tag:
            self.article.title = title_tag.get_text(strip=True)
        else:
            self.article.title = "Без заголовка"
        text_blocks = []
        content_div = article_soup.find('div', class_='composition_text')
        if content_div:
            text = content_div.get_text(separator='\n', strip=True)
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if len(line) > 20:
                    text_blocks.append(line)
        if not text_blocks:
            content_div = article_soup.find('td', class_='win offset')
            if content_div:
                text = content_div.get_text(separator='\n', strip=True)
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if (len(line) > 20 and
                        not line.startswith('Тип:') and
                        not line.startswith('Раздел:')):
                        text_blocks.append(line)
        self.article.text = '\n\n'.join(text_blocks)
        print(f"Article {self.article_id}: extracted {len(self.article.text)} characters")

    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        author_tag = (article_soup.find('div', class_='author') or
                  article_soup.find('span', class_='author'))
        if not author_tag:
            author_link = article_soup.find('a', href=re.compile(r'/autors_b\.php\?id='))
            if author_link:
                author_tag = author_link.find('span', itemprop='name') or author_link
        self.article.author = (
            [author_tag.get_text(strip=True)] if author_tag else ["NOT FOUND"]
        )
        date_text = None
        date_span = article_soup.find('span', itemprop='datePublished')
        date_tag = (article_soup.find('div', class_='date') or
                    article_soup.find('span', class_='date'))
        date_text = (date_span and date_span.get_text(strip=True)) or \
                    (date_tag and date_tag.get_text(strip=True))
        if not date_text:
            for cell in article_soup.find_all('td'):
                if 'Дата:' in cell.get_text():
                    date_text = cell.get_text().replace('Дата:', '').strip()
                    break
        if date_text:
            self.article.date = self.unify_date_format(date_text)
            date_set = True
        else:
            date_set = False
            for text in article_soup.stripped_strings:
                match = re.search(r'(\d{2}):(\d{2})\s+(\d{2})\.(\d{2})\.(\d{4})', text)
                if match:
                    parts = match.groups()
                    self.article.date = datetime.datetime(
                        int(parts[4]), int(parts[3]), int(parts[2]),
                        int(parts[0]), int(parts[1]), 0
                    )
                    date_set = True
                    break
        if not date_set:
            self.article.date = datetime.datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        topics = []
        for tag in (article_soup.find_all('a', class_='topic') or
                    article_soup.find_all('div', class_='category')):
            topic_text = tag.get_text(strip=True)
            if topic_text and topic_text not in topics:
                topics.append(topic_text)
        self.article.topics = topics

    def unify_date_format(self, date_str: str) -> datetime.datetime:
        """
        Unify date format.

        Args:
            date_str (str): Date in text format

        Returns:
            datetime.datetime: Datetime object
        """
        date_str = date_str.strip()
        try:
            return datetime.datetime.strptime(date_str, '%H:%M %d.%m.%Y')
        except ValueError:
            pass
        match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', date_str)
        if match:
            day, month, year = match.groups()
            return datetime.datetime(int(year), int(month), int(day), 0, 0, 0)
        return datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    def parse(self) -> Article | bool:
        """
        Parse each article.

        Returns:
            Article | bool: Article instance, False in case of request error
        """
        response = make_request(self.full_url, self.config)
        if not response or response.status_code != 200:
            return False
        soup = BeautifulSoup(response.content, 'html.parser')
        self._fill_article_with_text(soup)
        self._fill_article_with_meta_information(soup)
        return self.article


def prepare_environment(base_path: pathlib.Path | str) -> None:
    """
    Create ASSETS_PATH folder if no created and remove existing folder.

    Args:
        base_path (pathlib.Path | str): Path where articles stores
    """
    path = pathlib.Path(base_path)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    """
    Entrypoint for scraper module.
    """
    saved_count = 0
    config = Config(CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)
    crawler = Crawler(config)
    crawler.find_articles()
    for idx, url in enumerate(crawler.urls[:config.get_num_articles()], 1):
        parser = HTMLParser(url, idx, config)
        article = parser.parse()
        if isinstance(article, Article) and len(article.text) > 50:
            to_raw(article)
            to_meta(article)
            saved_count += 1
            print(f"Saved article {idx}: {url}")


if __name__ == "__main__":
    main()
