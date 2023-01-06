
from typing import Union
from textwrap import dedent
from redmail import EmailSender

from convert import remove_email_content_id, prune_generated_headers

def test_distributions():
    class DistrSender(EmailSender):
        "Send email using pre-defined distribution lists"

        def __init__(self, *args, distribution:dict, **kwargs):
            super().__init__(*args, **kwargs)
            self.distributions = distribution

        def get_receivers(self, receiver_list):
            if receiver_list:
                return self.distributions[receiver_list]

        def get_cc(self, receiver_list):
            if receiver_list:
                return self.distributions[receiver_list]

        def get_bcc(self, receiver_list):
            if receiver_list:
                return self.distributions[receiver_list]

    email = DistrSender(
        host="localhost", 
        port=0,
        distribution={
            'group1': ["me@example.com", "you@example.com"],
            'group2': ["he@example.com", "she@example.com"],
        }
    )

    msg = email.get_message(
        sender="me@example.com",
        receivers="group1",
        cc="group2",
        subject="Some email",
    )
    msg = prune_generated_headers(str(msg))
    msg = remove_email_content_id(str(msg))
    assert msg == dedent("""
    from: me@example.com
    subject: Some email
    to: me@example.com, you@example.com
    cc: he@example.com, she@example.com
    Message-ID: <<message_id>>
    Date: <date>
    
    """)[1:]