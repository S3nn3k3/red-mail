
from email.message import EmailMessage
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

import jinja2
from redmail.email.attachment import Attachments

from redmail.email.body import HTMLBody, TextBody
from redmail.models import EmailAddress, Error
from .envs import get_span, is_last_group_row

import smtplib

from pathlib import Path
from platform import node
from getpass import getuser
import datetime
import os

if TYPE_CHECKING:
    # These are never imported but just for linters
    import pandas as pd
    from PIL.Image import Image
    import matplotlib.pyplot as plt

class EmailSender:
    """Red Mail Email Sender

    Parameters
    ----------
    host : str
        SMTP host address.
    port : int
        Port to the SMTP server.
    user_name : str, optional
        User name to authenticate on the server.
    password : str, optional
        User password to authenticate on the server.
    cls_smtp : smtplib.SMTP
        SMTP class to use for connection. See options 
        from `Python smtplib docs <https://docs.python.org/3/library/smtplib.html>`_.
    use_starttls : bool
        Whether to use `STARTTLS <https://en.wikipedia.org/wiki/Opportunistic_TLS>`_ 
        when connecting to the SMTP server.
    **kwargs : dict
        Additional keyword arguments are passed to initiation in ``cls_smtp``.
        These are stored as attribute ``kws_smtp``

    Attributes
    ----------
    sender : str
        Address for sending emails if it is not specified
        in the send method.
    receivers : list of str
        Addresses to send emails if not specified
        in the send method.
    cc : list of str
        Carbon copies of emails if not specified
        in the send method.
    bcc : list of str
        Blind carbon copies of emails if not specified
        in the send method.
    subject : str
        Subject of emails if not specified
        in the send method.
    text : str
        Text body of emails if not specified
        in the send method.
    html : str
        HTML body of emails if not specified
        in the send method.
    text_template : str
        Name of the template to use as the text body of emails 
        if not specified in the send method. 
    html_template : str
        Name of the template to use as the HTML body of emails 
        if not specified in the send method.
    templates_html : jinja2.Environment
        Jinja environment used for loading HTML templates
        if ``html_template`` is specified in send.
    templates_text : jinja2.Environment
        Jinja environment used for loading text templates
        if ``text_template`` is specified in send.
    default_html_theme : str
        Jinja template from ``templates_html_table``
        used for styling tables for HTML body.
    default_text_theme : str
        Jinja template from ``templates_text_table``
        used for styling tables for text body.
    templates_html_table : jinja2.Environment
        Jinja environment used for loading templates
        for table styling for HTML bodies.
    templates_text_table : jinja2.Environment
        Jinja environment used for loading templates
        for table styling for text bodies.
    kws_smtp : dict
        Keyword arguments passed to ``cls_smtp``
        when connecting to the SMTP server.

    Examples
    --------
    .. code-block:: python

        email = EmailSender(server="smtp.mymail.com", port=123)
        email.send(
            subject="Example Email",
            sender="me@example.com",
            receivers=["you@example.com"],
        )
    """
    
    default_html_theme = "modest.html"
    default_text_theme = "pandas.txt"

    templates_html = jinja2.Environment(loader=jinja2.FileSystemLoader(str(Path(__file__).parent / "templates/html")))
    templates_html_table = jinja2.Environment(loader=jinja2.FileSystemLoader(str(Path(__file__).parent / "templates/html/table")))

    templates_text = jinja2.Environment(loader=jinja2.FileSystemLoader(str(Path(__file__).parent / "templates/text")))
    templates_text_table = jinja2.Environment(loader=jinja2.FileSystemLoader(str(Path(__file__).parent / "templates/text/table")))

    # Set globals
    templates_html_table.globals["get_span"] = get_span
    templates_text_table.globals["get_span"] = get_span
    
    templates_html_table.globals["is_last_group_row"] = is_last_group_row
    templates_text_table.globals["is_last_group_row"] = is_last_group_row

    attachment_encoding = 'UTF-8'

    def __init__(self, host:str, port:int, user_name:str=None, password:str=None, cls_smtp:smtplib.SMTP=smtplib.SMTP, use_starttls:bool=True, **kwargs):
        self.host = host
        self.port = port

        self.user_name = user_name
        self.password = password

        # Defaults
        self.sender = None
        self.receivers = None
        self.cc = None
        self.bcc = None
        self.subject = None

        self.text = None
        self.html = None
        self.html_template = None
        self.text_template = None

        self.use_starttls = use_starttls
        self.cls_smtp = cls_smtp
        self.kws_smtp = kwargs
        
    def send(self,
             subject:Optional[str]=None,
             sender:Optional[str]=None,
             receivers:Union[List[str], str, None]=None,
             cc:Union[List[str], str, None]=None,
             bcc:Union[List[str], str, None]=None,
             html:Optional[str]=None,
             text:Optional[str]=None,
             html_template:Optional[str]=None,
             text_template:Optional[str]=None,
             body_images:Optional[Dict[str, Union[str, bytes, 'plt.Figure', 'Image']]]=None, 
             body_tables:Optional[Dict[str, 'pd.DataFrame']]=None, 
             body_params:Optional[Dict[str, Any]]=None,
             attachments:Optional[Dict[str, Union[str, os.PathLike, 'pd.DataFrame', bytes]]]=None) -> EmailMessage:
        """Send an email.

        Parameters
        ----------
        subject : str
            Subject of the email.
        sender : str, optional
            Email address the email is sent from.
            Note that some email services might not 
            respect changing sender address 
            (for example Gmail).
        receivers : list, optional
            Receivers of the email.
        cc : list, optional
            Cc or Carbon Copy of the email.
            Additional recipients of the email.
        bcc : list, optional
            Blind Carbon Copy of the email.
            Additional recipients of the email that
            don't see who else got the email.
        html : str, optional
            HTML body of the email. This is processed
            by Jinja and may contain loops, parametrization
            etc. See `Jinja documentation <https://jinja.palletsprojects.com>`_.
        text : str, optional
            Text body of the email. This is processed
            by Jinja and may contain loops, parametrization
            etc. See `Jinja documentation <https://jinja.palletsprojects.com>`_.
        html_template : str, optional
            Name of the HTML template loaded using Jinja environment specified
            in ``templates_html`` attribute. Specify either ``html`` or ``html_template``.
        text_template : str, optional
            Name of the text template loaded using Jinja environment specified
            in ``templates_text`` attribute. Specify either ``text`` or ``text_template``.
        body_images : dict of bytes, dict of path-like, dict of plt Figure, dict of PIL Image, optional
            HTML images to embed with the html. The key should be 
            as Jinja variables in the html and the values represent
            images (path to an image, bytes of an image or image object).
        body_tables : dict of Pandas dataframes, optional
            HTML tables to embed with the html. The key should be 
            as Jinja variables in the html and the values are Pandas
            DataFrames.
        body_params : dict, optional
            Extra Jinja parameters passed to the HTML and text bodies.
        attachments : dict, optional
            Attachments of the email. If dict value is string, the attachment content
            is the string itself. If path, the attachment is the content of the path's file.
            If dataframe, the dataframe is turned to bytes or text according to the 
            file extension in dict key.

        Examples
        --------
        
            Simple example:

            .. code-block:: python

                from redmail import EmailSender

                email = EmailSender(
                    host='localhost', 
                    port=0, 
                    user_name='me@example.com', 
                    password='<PASSWORD>'
                )
                email.send(
                    subject="An email",
                    sender="me@example.com",
                    receivers=['you@example.com'],
                    test="Hi, this is an email.",
                    html="<h1>Hi, </h1><p>this is an email.</p>"
                )

            See more examples from :ref:`docs <examples>`

        Returns
        -------
        EmailMessage
            Email message.

        Notes
        -----
            See also `Jinja documentation <https://jinja.palletsprojects.com>`_
            for utilizing Jinja in ``html`` and ``text`` arguments or for using 
            Jinja templates with  ``html_template`` and ``text_template`` arguments.
        """
        msg = self.get_message(
            subject=subject,
            sender=sender,
            receivers=receivers,
            cc=cc,
            bcc=bcc,
            html=html,
            text=text,
            html_template=html_template,
            text_template=text_template,
            body_images=body_images,
            body_tables=body_tables,
            body_params=body_params,
            attachments=attachments,
        )
        self.send_message(msg)
        return msg
        
    def get_message(self, 
                  subject:Optional[str]=None,
                  sender:Optional[str]=None,
                  receivers:Union[List[str], str, None]=None,
                  cc:Union[List[str], str, None]=None,
                  bcc:Union[List[str], str, None]=None,
                  html:Optional[str]=None,
                  text:Optional[str]=None,
                  html_template:Optional[str]=None,
                  text_template:Optional[str]=None,
                  body_images:Optional[Dict[str, Union[str, bytes, 'plt.Figure', 'Image']]]=None, 
                  body_tables:Optional[Dict[str, 'pd.DataFrame']]=None, 
                  body_params:Optional[Dict[str, Any]]=None,
                  attachments:Optional[Dict[str, Union[str, os.PathLike, 'pd.DataFrame', bytes]]]=None) -> EmailMessage:
        """Get the email message"""

        subject = subject or self.subject
        sender = self.get_sender(sender)

        receivers = self.get_receivers(receivers)
        cc = self.get_cc(cc)
        bcc = self.get_bcc(bcc)

        html = html or self.html
        text = text or self.text
        html_template = html_template or self.html_template
        text_template = text_template or self.text_template

        if subject is None:
            raise ValueError("Email must have a subject")

        msg = self._create_body(
            subject=subject, 
            sender=sender, 
            receivers=receivers,
            cc=cc,
            bcc=bcc,
        )

        if text is not None or text_template is not None:
            body = TextBody(
                template=self.get_text_template(text_template),
                table_template=self.get_text_table_template(),
            )
            body.attach(
                msg, 
                text, 
                tables=body_tables,
                jinja_params=self.get_text_params(extra=body_params, sender=sender),
            )

        if html is not None or html_template is not None:
            body = HTMLBody(
                template=self.get_html_template(html_template),
                table_template=self.get_html_table_template(),
            )
            body.attach(
                msg,
                html=html,
                images=body_images,
                tables=body_tables,
                jinja_params=self.get_html_params(extra=body_params, sender=sender)
            )
        if attachments:
            att = Attachments(attachments, encoding=self.attachment_encoding)
            att.attach(msg)
        return msg

    def get_receivers(self, receivers:Union[list, str, None]) -> Union[List[str], None]:
        """Get receivers of the email"""
        return receivers or self.receivers

    def get_cc(self, cc:Union[list, str, None]) -> Union[List[str], None]:
        """Get carbon copy (cc) of the email"""
        return cc or self.cc

    def get_bcc(self, bcc:Union[list, str, None]) -> Union[List[str], None]:
        """Get blind carbon copy (bcc) of the email"""
        return bcc or self.bcc

    def get_sender(self, sender:Union[str, None]) -> str:
        """Get sender of the email"""
        return sender or self.sender or self.user_name

    def _create_body(self, subject, sender, receivers=None, cc=None, bcc=None) -> EmailMessage:
        msg = EmailMessage()
        msg["from"] = sender
        msg["subject"] = subject
        
        # To whoom the email goes
        if receivers:
            msg["to"] = receivers
        if cc:
            msg['cc'] = cc
        if bcc:
            msg['bcc'] = bcc
        return msg

    def send_message(self, msg:EmailMessage):
        "Send the created message"

        server = self.connect()
        server.send_message(msg)
        
        server.quit()
    
    def connect(self) -> smtplib.SMTP:
        "Connect to the SMTP Server"
        user = self.user_name
        password = self.password
        
        server = self.cls_smtp(self.host, self.port, **self.kws_smtp)
        if self.use_starttls:
            server.starttls()

        if user is not None or password is not None:
            server.login(user, password)
        return server

    def get_params(self, sender:str) -> Dict[str, Any]:
        "Get Jinja parametes passed to both text and html bodies"
        # TODO: Add receivers to params
        return {
            "node": node(),
            "user": getuser(),
            "now": datetime.datetime.now(),
            "sender": EmailAddress(sender),
        }

    def get_html_params(self, extra:Optional[dict]=None, **kwargs) -> Dict[str, Any]:
        "Get Jinja parameters passed to HTML body"
        params = self.get_params(**kwargs)
        params.update({
            "error": Error(content_type='html-inline')
        })
        if extra:
            params.update(extra)
        return params

    def get_text_params(self, extra:Optional[dict]=None, **kwargs) -> Dict[str, Any]:
        "Get Jinja parameters passed to text body"
        params = self.get_params(**kwargs)
        params.update({
            "error": Error(content_type='text')
        })
        if extra:
            params.update(extra)
        return params

    def get_html_table_template(self, layout:Optional[str]=None) -> Union[jinja2.Template, None]:
        "Get Jinja template for tables in HTML body"
        layout = self.default_html_theme if layout is None else layout
        if layout is None:
            return None
        return self.templates_html_table.get_template(layout)

    def get_html_template(self, layout:Optional[str]=None) -> Union[jinja2.Template, None]:
        "Get pre-made Jinja template for HTML body"
        if layout is None:
            return None
        return self.templates_html.get_template(layout)

    def get_text_table_template(self, layout:Optional[str]=None) -> jinja2.Template:
        "Get Jinja template for tables in text body"
        layout = self.default_text_theme if layout is None else layout
        if layout is None:
            return None
        return self.templates_text_table.get_template(layout)

    def get_text_template(self, layout:Optional[str]=None) -> jinja2.Template:
        "Get pre-made Jinja template for text body"
        if layout is None:
            return None
        return self.templates_text.get_template(layout)

    def set_template_paths(self, 
                           html:Union[str, os.PathLike, None]=None, 
                           text:Union[str, os.PathLike, None]=None, 
                           html_table:Union[str, os.PathLike, None]=None, 
                           text_table:Union[str, os.PathLike, None]=None):
        """Create Jinja envs for body templates using given paths
        
        This is a shortcut for manually setting them:

        .. code-block:: python

            sender.templates_html = jinja2.Environment(loader=jinja2.FileSystemLoader(...))
            sender.templates_text = jinja2.Environment(loader=jinja2.FileSystemLoader(...))
            sender.templates_html_table = jinja2.Environment(loader=jinja2.FileSystemLoader(...))
            sender.templates_text_table = jinja2.Environment(loader=jinja2.FileSystemLoader(...))
        """
        if html is not None:
            self.templates_html = jinja2.Environment(loader=jinja2.FileSystemLoader(html))
        if text is not None:
            self.templates_text = jinja2.Environment(loader=jinja2.FileSystemLoader(text))
        if html_table is not None:
            self.templates_html_table = jinja2.Environment(loader=jinja2.FileSystemLoader(html_table))
        if text_table is not None:
            self.templates_text_table = jinja2.Environment(loader=jinja2.FileSystemLoader(text_table))