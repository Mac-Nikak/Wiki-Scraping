import aiohttp
import asyncio
import re
import time
import aiofiles
import argparse

MAIN_PAGE = {'https://ru.wikipedia.org/wiki/%D0%97%D0%B0%D0%B3%D0%BB%D0%B0%D0%B2%D0%BD%D0%B0%D1%8F_%D1%81%D1%82%D1%80'
             '%D0%B0%D0%BD%D0%B8%D1%86%D0%B0', 'https://ru.wikipedia.org/wiki/'}
storage = set()


async def get_html(url: str, session: aiohttp.ClientSession) -> str:
    try:
        async with session.get(url) as response:
            html_text = await response.text()
            response.close()
            return html_text
    except aiohttp.ClientPayloadError:  # it is extremely bad idea, cause we lose data, but it is quiet
        print('Error!')  # save, as it eliminates situations when we catch this exception.
        response.close()  # I tried to solve this issue different ways as opening new session, if
        return ''  # we catch this exception but I caught it anyways.


async def find_links(raw_html: str) -> list:
    re_comp = re.compile(r'href="(.*?)"')
    raw_links = re_comp.findall(raw_html)
    links = ['https://ru.wikipedia.org' + link for link in raw_links
             if link[0:5] == '/wiki' and link.find(':') == -1
             and 'https://ru.wikipedia.org' + link not in MAIN_PAGE
             and 'https://ru.wikipedia.org' + link not in storage]  # big list with all necessary conditions
    return links


def get_title(html: str) -> str:
    start = html.find('<title>') + 7  # Every HTML file contains title of the web-page, so here I get it
    end = html.find('</title>')
    return html[start:end]


async def check_if_in3(goal_title: str, link_html: str, q: asyncio.Queue,
                       source: str, ancestors: list, links: list) -> bool:
    link_title = get_title(link_html)  # just straightforward comparison of web-pages titles
    if link_title == goal_title:
        return True
    else:
        new_ancestors = ancestors.copy()
        new_ancestors.append(source)  # list of ancestors of the file
        for link in links:
            await q.put((link, new_ancestors))  # adding links from web-page to queue
            storage.add(link)  # in order not to analyse same pages
        return False


async def process_one_url(source: str, ancestors: list, session: aiohttp.ClientSession,
                          queue: asyncio.Queue,
                          goal_title: str) -> None:  # chaining coroutines
    raw_html = await get_html(source, session)
    links = await find_links(raw_html)
    check = await check_if_in3(goal_title, raw_html, queue, source, ancestors, links)
    if check:  # if we found web-page we were searching for just cancel all tasks in the event-loop
        ancestors.append(source)  # print all ancestors
        print(*ancestors)
        for task in (task for task in asyncio.all_tasks() if not task.done()):
            task.cancel()


async def print_message(i: int, j: int, start: float) -> None:
    async with aiofiles.open('output.txt', 'w') as file:
        text = f'We have checked {j} links, nothing found {i}, process ended in {time.time() - start} seconds.'
        print(text)
        await file.write(text + '\n')


async def main(source: str, goal: str, n: int) -> None:
    q = asyncio.Queue()
    storage.add(source)
    async with aiohttp.ClientSession() as session:
        await q.put((source, []))
        goal_title = get_title(await get_html(goal, session))  # getting title of our goal
        i = 0  # not really useful made just for calculation
        j = 0
        await session.close()
    while True:
        async with aiohttp.ClientSession() as session:
            try:
                start = time.time()
                z = min(n, q.qsize())
                coros1 = (q.get() for i in range(z))    # generator with coros which get tasks to get elements out
                links = await asyncio.gather(*coros1)   # of queue
                coros = (process_one_url(
                    x[0], x[1], session, q, goal_title) for x in links
                )                                       # generator with tasks to analyse one url
                await asyncio.gather(*coros)
                i += 1
                j += z
                await session.close()
                if i % 1 == 0:
                    await print_message(i, j, start)
            except asyncio.exceptions.CancelledError:
                print('Result found!')
                break


if __name__ == '__main__':
    parser = argparse.ArgumentParser()    # simple magic to make our program execute in command line without pain.
    parser.add_argument('-s', '--source', default='https://ru.wikipedia.org/wiki/%D0%92%D0%BE%D1%80%D0%BE%D0%BD')
    parser.add_argument('-g', '--goal', default='https://ru.wikipedia.org/wiki/%D0%9F%D0%B8%D1%81%D1%8C%D0%BC%D0%B5'
                                                '%D0%BD%D0%BD%D1%8B%D0%B9_%D1%81%D1%82%D0%BE%D0%BB')
    parser.add_argument('-n', '--number', type=int, default=32)
    args = parser.parse_args()
    asyncio.run(main(args.source, args.goal, args.number))
