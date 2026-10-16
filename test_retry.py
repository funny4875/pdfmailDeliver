import unittest
import threading
from unittest.mock import patch
from retry_runner import run_delivery
from pdfmailDeliver import MailSender, App, ConfigManager

class RetryTests(unittest.TestCase):
    def simulate(self, outcomes, duration=100000, cancel=False):
        now=[0]; calls=[]; reports=[]; stop=threading.Event()
        jobs=[dict(name=str(i), email='test@example.invalid', subject='original', body='original body', file_path='original.pdf') for i in range(len(outcomes))]
        def send(job):
            i=int(job['name']); calls.append((i, now[0], dict(job)))
            answer=outcomes[i].pop(0) if len(outcomes[i])>1 else outcomes[i][0]
            return answer == 'OK', answer
        def wait(seconds):
            now[0]+=seconds
            if cancel: stop.set()
            return stop.is_set()
        states=run_delivery(jobs,send,duration,stop,lambda _:None,lambda *args:None,lambda s:reports.append(list(s)),lambda:0,lambda:now[0],wait)
        return calls, states

    def test_exponential_cap_deadline(self):
        calls,states=self.simulate([['Server not connected']],24000)
        times=[t for _,t,_ in calls]
        self.assertEqual([b-a for a,b in zip(times,times[1:])], [120,240,480,960,1920,3840,7200,7200])
        self.assertLess(times[-1],24000)

    def test_success_resets_and_other_errors_not_retried(self):
        calls,states=self.simulate([['Server not connected','Server not connected','OK'],['Server not connected'],['bad password']],1000)
        self.assertEqual([t for i,t,_ in calls if i==1], [0,120,360,480,720])
        self.assertEqual(sum(i==0 for i,_,_ in calls),3)
        self.assertEqual(sum(i==2 for i,_,_ in calls),1)
        for _,_,job in calls:
            self.assertEqual((job['subject'],job['body'],job['file_path']),('original','original body','original.pdf'))

    def test_stop_and_deadline(self):
        self.assertEqual(len(self.simulate([['Server not connected']],119)[0]),1)
        self.assertEqual(len(self.simulate([['Server not connected']],1000,True)[0]),1)
        self.assertEqual(len(self.simulate([['OK']])[0]),1)

    def test_quit_failure_is_success(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory, patch('pdfmailDeliver.smtplib.SMTP_SSL') as smtp:
            from pathlib import Path
            attachment = Path(directory) / 'test.pdf'
            attachment.write_bytes(b'%PDF-test')
            smtp.return_value.quit.side_effect=Exception('Server not connected')
            self.assertEqual(MailSender.send('a','b','c','subject','body',str(attachment)),(True,'成功'))
            smtp.return_value.send_message.assert_called_once()

    def test_missing_attachment(self):
        with patch('pdfmailDeliver.smtplib.SMTP_SSL') as smtp:
            self.assertFalse(MailSender.send('a','b','c','s','b','not-present.pdf')[0])
            smtp.assert_not_called()

    def test_actual_ui(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory, patch.object(ConfigManager, 'get_app_path', return_value=directory):
            app=App(); app.update()
            self.assertEqual(app.entry_hours.get(),'24')
            self.assertEqual(str(app.btn_stop['state']),'disabled')
            app.hours_var.set('12.5')
            app.close_window()
            self.assertEqual(ConfigManager.load()['retry_hours'], '12.5')
            ConfigManager.save('a', 'b', directory, '15')
            app=App(); app.update()
            self.assertEqual(app.entry_hours.get(),'12.5')
            app.hours_var.set('-1')
            app.close_window()
            self.assertEqual(ConfigManager.load()['retry_hours'], '12.5')

if __name__=='__main__': unittest.main(verbosity=2)
