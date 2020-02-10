# -*- coding: utf-8 -*-
import asyncio
import logging
import time
import traceback

from .data_objects import Image, RedditImage, TagCollection, WikiHowImage, Ban, BanIterator
from .errors import APIError
from .events import BanEvent, UnBanEvent
from .http import HttpClient, Route
from .apis import ban

logger = logging.getLogger()


class Client:
    """
    .. _aiohttp session: https://aiohttp.readthedocs.io/en/stable/client_reference.html#client-session

    Client object for KSOFT.SI API

    This is a client object for KSoft.Si API. Here are two versions. Basic without discord.py bot
    and a pluggable version that inserts this client object directly into your discord.py bot.


    Represents a client connection that connects to ksoft.si. It works in two modes:
        1. As a standalone variable.
        2. Plugged-in to discord.py Bot or AutoShardedBot, see :any:`Client.pluggable`

    Parameters
    -------------
    api_key: :class:`str`
        Your ksoft.si api token.
        Specify different base url.
    **bot: Bot or AutoShardedBot
        Your bot client from discord.py
    **loop: asyncio loop
        Your asyncio loop.
    """

    def __init__(self, api_key: str, bot=None, loop=asyncio.get_event_loop()):
        self.api_key = api_key
        self._loop = loop
        self.http = HttpClient(authorization=self.api_key, loop=self._loop)
        self.bot = bot

        self._ban_hook = []
        self._last_update = time.time() - 60 * 10

        if self.bot is not None:
            loop.create_task(self._ban_updater)

        ##############
        #    APIS    #
        ##############
        self._ban_api = ban.Ban(self)

    def register_ban_hook(self, func):
        if func not in self._ban_hook:
            logger.debug('Registered event hook with name %s', func.__name__)
            self._ban_hook.append(func)

    def unregister_ban_hook(self, func):
        if func in self._ban_hook:
            logger.debug('Unregistered event hook with name %s', func.__name__)
            self._ban_hook.remove(func)

    async def _dispatch_ban_event(self, event):
        logger.debug('Dispatching event of type %s to %d hooks', event.__class__.__name__, len(self._ban_hook))
        for hook in self._ban_hook:
            try:
                await hook(event)
            except Exception as exc:
                logger.warning('Event hook "%s" encountered an exception', func.__name__, exc_info=exc)

    async def _ban_updater(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                if self._ban_hook:
                    route = Route.bans('GET', '/updates')
                    r = await self.http.get('/updates', params={'timestamp': self._last_update}, json=True)
                    self._last_update = time.time()
                    for b in r['data']:
                        event = BanEvent(**b) if b['active'] else UnBanEvent(**b)
                        await self._dispatch_ban_event(event)
            except Exception as exc:
                logger.error('An error occurred within the ban update loop', exc_info=exc)
            finally:
                await asyncio.sleep(60 * 5)

    @classmethod
    def pluggable(cls, bot, api_key: str, *args, **kwargs):
        """
        Pluggable version of Client. Inserts Client directly into your Bot client.
        Called by using `bot.ksoft`

        Parameters
        -------------
        bot: discord.ext.commands.Bot or discord.ext.commands.AutoShardedBot
            Your bot client from discord.py
        api_key: :class:`str`
            Your ksoft.si api token.

        .. note::
            Takes the same parameters as :class:`Client` class.
            Usage changes to ``bot.ksoft``. (``bot`` is your bot client variable)
        """
        try:
            return bot.ksoft
        except AttributeError:
            bot.ksoft = cls(api_key, bot=bot, *args, **kwargs)
            return bot.ksoft

    @property
    def bans(self):
        return self._ban_api

    async def tags(self) -> TagCollection:
        """|coro|
        This function gets all available tags on the api.

        :return: :class:`ksoftapi.data_objects.TagCollection`
        """
        g = await self.http.request(Route.meme("GET", "/tags"))
        return TagCollection(**g)

    # BANS
