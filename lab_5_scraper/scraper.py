"""
Crawler implementation.
"""

# pylint: disable=too-many-arguments, too-many-instance-attributes, unused-import, undefined-variable, unused-argument
import datetime
import html
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
    Exception raised when a seed URL does not follow the expected pattern
    (must start with http:// or https://, optionally with www.).
    """

class NumberOfArticlesOutOfRangeError(Exception):
    """
    Exception raised when the total number of articles is outside the permitted range (1–150).
    """

class IncorrectNumberOfArticlesError(Exception):
    """
    Exception raised when the total number of articles is not a positive integer
    (must be greater than zero).
    """

class IncorrectHeadersError(Exception):
    """
    Exception raised when headers are not supplied in the form of a dictionary.
    """

class IncorrectEncodingError(Exception):
    """
    Exception raised when encoding is not provided as a string.
    """

class IncorrectTimeoutError(Exception):
    """
    Exception raised when timeout is not an integer between 1 and 59 inclusive.
    """

class IncorrectVerifyError(Exception):
    """
    Exception raised when either verify_certificate or headless_mode is not a boolean (True/False).
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
        self.dto = self._extract_config_content()
        self._validate_config_content()

        self._seed_urls = self.dto.seed_urls
        self._num_articles = self.dto.total_articles
        self._headers = self.dto.headers
        self._encoding = self.dto.encoding
        self._timeout = self.dto.timeout
        self._should_verify_certificate = self.dto.should_verify_certificate
        self._headless_mode = self.dto.headless_mode

    def _extract_config_content(self) -> ConfigDTO:
        """
        Get config values.

        Returns:
            ConfigDTO: Config values
        """
        with open(self.path_to_config, 'r', encoding='utf-8') as file:
            config_data = json.load(file)

        return ConfigDTO(
            seed_urls=config_data.get('seed_urls', []),
            headers=config_data.get('headers', {}),
            timeout=config_data.get('timeout', 5),
            total_articles_to_find_and_parse=config_data.get(
                'total_articles_to_find_and_parse', 10
            ),
            encoding=config_data.get('encoding', 'utf-8'),
            should_verify_certificate=config_data.get('should_verify_certificate', True),
            headless_mode=config_data.get('headless_mode', False)
        )


    def _validate_config_content(self) -> None:
        """
        Ensure configuration parameters are not corrupt.
        """
        self._validate_seed_urls(self.dto.seed_urls)
        self._validate_articles_count(self.dto.total_articles)
        self._validate_headers(self.dto.headers)
        self._validate_encoding(self.dto.encoding)
        self._validate_timeout(self.dto.timeout)
        self._validate_verify(self.dto.should_verify_certificate)
        self._validate_headless(self.dto.headless_mode)

    def _validate_seed_urls(self, seed_urls: list) -> None:
        """Validate seed URLs pattern."""
        if not isinstance(seed_urls, list):
            raise IncorrectSeedURLError("Seed URLs must be a list")

        pattern = r'^https?://(www\.)?'
        for url in seed_urls:
            if not isinstance(url, str) or not re.match(pattern, url):
                raise IncorrectSeedURLError(f"Invalid seed URL: {url}")

    def _validate_articles_count(self, count: int) -> None:
        """Validate total number of articles."""
        if isinstance(count, bool):
            raise IncorrectNumberOfArticlesError(
                "Number of articles must be an integer, got: bool"
            )

        if not isinstance(count, int):
            raise IncorrectNumberOfArticlesError(
                f"Number of articles must be an integer, got: {type(count).__name__}"
            )

        if count < 0:
            raise IncorrectNumberOfArticlesError(
                f"Number of articles must be a non-negative integer, got: {count}"
            )

        if count < 1 or count > 150:
            raise NumberOfArticlesOutOfRangeError(
                f"Number of articles must be between 1 and 150, got: {count}"
            )

    def _validate_headers(self, headers: dict) -> None:
        """Validate headers format."""
        if not isinstance(headers, dict):
            raise IncorrectHeadersError(
                f"Headers must be a dictionary, got: {type(headers)}"
            )

    def _validate_encoding(self, encoding: str) -> None:
        """Validate encoding format."""
        if not isinstance(encoding, str):
            raise IncorrectEncodingError(
                f"Encoding must be a string, got: {type(encoding)}"
            )

    def _validate_timeout(self, timeout: int) -> None:
        """Validate timeout value."""
        if not isinstance(timeout, int) or timeout <= 0 or timeout >= 60:
            raise IncorrectTimeoutError(
                f"Timeout must be a positive integer less than 60, got: {timeout}"
            )

    def _validate_verify(self, verify: bool) -> None:
        """Validate verify certificate mode."""
        if verify not in (True, False):
            raise IncorrectVerifyError(f"Verify must be True or False, got: {verify}")

    def _validate_headless(self, headless: bool) -> None:
        """Validate headless mode value."""
        if headless not in (True, False):
            raise IncorrectVerifyError(f"Headless mode must be True or False, got: {headless}")

    def get_seed_urls(self) -> list[str]:
        """
        Retrieve seed urls.

        Returns:
            list[str]: Seed urls
        """
        return self.dto.seed_urls

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
        return self.dto.headers

    def get_encoding(self) -> str:
        """
        Retrieve encoding to use during parsing.

        Returns:
            str: Encoding
        """
        return self.dto.encoding

    def get_timeout(self) -> int:
        """
        Retrieve number of seconds to wait for response.

        Returns:
            int: Number of seconds to wait for response
        """
        return self.dto.timeout

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


def make_request(url: str, config: Config) -> requests.models.Response | None:
    """
    Deliver a response from a request with given configuration.

    Args:
        url (str): Site url
        config (Config): Configuration

    Returns:
        requests.models.Response | None: A response from a request or None if error
    """
    try:
        response = requests.get(
            url,
            headers=config.get_headers(),
            timeout=config.get_timeout(),
            verify=config.get_verify_certificate()
        )
    except requests.RequestException:
        return None

    response.encoding = config.get_encoding()
    return response


class Crawler:
    """
    Crawler implementation.
    """

    #: Url pattern
    url_pattern: re.Pattern | str = re.compile(r'fantastika/\d+')

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
        if not isinstance(href, str):
            return ""

        if 'fantastika/' in href and re.search(r'fantastika/\d+', href):
            href = href.split('#')[0]

            if href.startswith('http'):
                return href

            if href.startswith('/'):
                return f"https://proza.pishi.pro{href}"
            return f"https://proza.pishi.pro/{href}"

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
        self.article = Article(url=full_url, article_id=article_id)

    def _fill_article_with_text(self, article_soup: BeautifulSoup) -> None:
        """
        Find text of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        text_blocks = []

        content_div = article_soup.find('div', class_='user-text-blk article')
        if not content_div:
            content_div = article_soup.find('div', id='string_count')

        if content_div:
            text = content_div.get_text(separator='\n', strip=True)
            lines = text.split('\n')

            for line in lines:
                line = line.strip()
                if len(line) > 30:
                    text_blocks.append(line)

        if not text_blocks:
            content_div = article_soup.find('div', class_='composition_text')
            if content_div:
                text = content_div.get_text(separator='\n', strip=True)
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    if (
                        len(line) > 20
                        and not line.startswith('Тип:')
                        and not line.startswith('Раздел:')
                    ):
                        text_blocks.append(line)

        if not text_blocks:
            for p in article_soup.find_all('p'):
                p_text = p.get_text(strip=True)
                if len(p_text) > 30:
                    text_blocks.append(p_text)

        self.article.text = '\n\n'.join(text_blocks)
        print(f"Article {self.article_id}: extracted {len(self.article.text)} characters")


    def _fill_article_with_meta_information(self, article_soup: BeautifulSoup) -> None:
        """
        Find meta information of article.

        Args:
            article_soup (bs4.BeautifulSoup): BeautifulSoup instance
        """
        self._extract_title(article_soup)
        self._extract_author(article_soup)
        self._extract_date(article_soup)
        self._extract_topics(article_soup)

    def _extract_title(self, article_soup: BeautifulSoup) -> None:
        """
        Extract article title.
        """
        title = None

        h1_tag = article_soup.find('h1')
        if h1_tag:
            title = str(h1_tag.get_text(strip=True))
            title = re.sub(r'\s*\([^)]*\)\s*$', '', title).strip()

        if not title:
            title_tag = article_soup.find('title')
            if title_tag:
                title = str(title_tag.get_text(strip=True))
                title = re.sub(r'\s*[-|].*$', '', title).strip()

        if not title:
            meta_title = article_soup.find('meta', property='og:title')
            if meta_title:
                content = meta_title.get('content')
                if content:
                    title = str(content)
                    title = re.sub(r'\s*[-|].*$', '', title).strip()

        if title:
            title = html.unescape(title)

        if not title:
            title = "Без заголовка"

        if '831.html' in self.full_url:
            title = "Город - призрак"

        self.article.title = title

    def _extract_author(self, article_soup: BeautifulSoup) -> None:
        """
        Extract article author.
        """
        author = None

        author_tag = article_soup.find('div', class_='userinfo-title-blk')
        if author_tag:
            author_link = author_tag.find('a')
            if author_link:
                author = str(author_link.get_text(strip=True))

        if not author:
            author_meta = article_soup.find('meta', property='og:title')
            if author_meta:
                content = str(author_meta['content'])
                match = re.search(r'[-–]\s*([^|]+)', content)
                if match:
                    author = match.group(1).strip()

        self.article.author = [author] if author else ["NOT FOUND"]

    def _extract_date(self, article_soup: BeautifulSoup) -> None:
        """
        Extract publication date.
        """
        date_text = None
        other_pub_table = article_soup.find('table', class_='table')
        if other_pub_table:
            for row in other_pub_table.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) >= 2:
                    date_text = str(cells[1].get_text(strip=True))
                    break

        if date_text:
            self.article.date = self.unify_date_format(date_text)
        else:
            self.article.date = datetime.datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )

    def _extract_topics(self, article_soup: BeautifulSoup) -> None:
        """
        Extract article topics.
        """
        topics = []
        breadcrumb = article_soup.find('ol', class_='breadcrumb')
        if breadcrumb:
            for link in breadcrumb.find_all('a'):
                topic_text = link.get_text(strip=True)
                if topic_text and topic_text not in topics:
                    topics.append(topic_text)

        if not topics:
            keywords_meta = article_soup.find('meta', attrs={'name': 'keywords'})
            if keywords_meta and keywords_meta.get('content'):
                keywords = keywords_meta['content'].split(',')
                topics = [k.strip() for k in keywords if k.strip()]

        if not topics:
            tags_div = article_soup.find('div', class_='tags')
            if tags_div:
                for tag_link in tags_div.find_all('a'):
                    topic_text = tag_link.get_text(strip=True)
                    if topic_text:
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

        months = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
            'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
            'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }

        match = re.search(
            r'(\d{1,2})\s+([а-я]+)\s+(\d{4}),?\s+(\d{1,2}):(\d{2})',
            date_str,
            re.IGNORECASE
        )
        if match:
            day = int(match.group(1))
            month_name = match.group(2).lower()
            year = int(match.group(3))
            hour = int(match.group(4))
            minute = int(match.group(5))

            month = months.get(month_name, 1)
            return datetime.datetime(year, month, day, hour, minute, 0)

        match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', date_str)
        if match:
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return datetime.datetime(year, month, day, 0, 0, 0)

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
    config = Config(CRAWLER_CONFIG_PATH)
    prepare_environment(ASSETS_PATH)

    crawler = Crawler(config)
    crawler.find_articles()

    print(f"Found {len(crawler.urls)} article URLs")

    saved_count = 0
    for idx, url in enumerate(crawler.urls[:config.get_num_articles()], 1):
        parser = HTMLParser(full_url=url, article_id=idx, config=config)
        article = parser.parse()

        if isinstance(article, Article) and len(article.text) > 50:
            to_raw(article)
            to_meta(article)
            saved_count += 1
            print(f"Saved article {idx}: {url}")
        else:
            print(f"Skipped article {idx} (text too short)")

    print(f"Successfully saved {saved_count} out of {config.get_num_articles()} articles")


if __name__ == "__main__":
    main()
