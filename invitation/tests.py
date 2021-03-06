"""
Unit tests for django-invitation.

These tests assume that you've completed all the prerequisites for
getting django-invitation running in the default setup, to wit:

1. You have ``invitation`` in your ``INSTALLED_APPS`` setting.

2. You have created all of the templates mentioned in this
   application's documentation.

3. You have added the setting ``ACCOUNT_INVITATION_DAYS`` to your
   settings file.

4. You have URL patterns pointing to the invitation views.

"""

import datetime
import hashlib

from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.core import management
from django.core.urlresolvers import reverse
from django.test import TestCase
from django.contrib.sites.models import Site


from invitation import forms
from invitation.models import InvitationKey, InvitationUser

allauth_installed = False 
try:
    if 'allauth' in settings.INSTALLED_APPS:
        allauth_installed = True
        print("** allauth installed **")
    from allauth.socialaccount.models import SocialApp
except:
    pass

registration_installed = False    
try: 
    import registration
    if 'registration' in settings.INSTALLED_APPS:
        registration_installed = True
        print("** registration installed **")
except:
    pass        

    
class InvitationTestCase(TestCase):
    """
    Base class for the test cases.
    
    This sets up one user and two keys -- one expired, one not -- which are 
    used to exercise various parts of the application.
    
    """
    def setUp(self):        
        self.sample_user = User.objects.create_user(username='alice',
                                                    password='secret',
                                                    email='alice@example.com')
        self.sample_key = InvitationKey.objects.create_invitation(user=self.sample_user)
        self.expired_key = InvitationKey.objects.create_invitation(user=self.sample_user)
        self.expired_key.date_invited -= datetime.timedelta(days=settings.ACCOUNT_INVITATION_DAYS + 1)
        self.expired_key.save()
        
        self.sample_registration_data = {
            'invitation_key': self.sample_key.key,
            'username': 'new_user',
            'email': 'newbie@example.com',
            'password1': 'secret',
            'password2': 'secret',
            'tos': '1'}
        
        self.sample_allauth_data = {
            'username': 'new_user',
            'email': 'newbie@example.com',
            'password1': 'secret',
            'password2': 'secret',
            'terms_and_conds': '1'}     

    def assertRedirect(self, response, viewname):
        """Assert that response has been redirected to ``viewname``."""
        self.assertEqual(response.status_code, 302)
        expected_location = 'http://testserver' + reverse(viewname)
        self.assertEqual(response['Location'], expected_location)      

    def tearDown(self):
        pass

class InvitationTestCaseRegistration(InvitationTestCase):
    
    def setUp(self):
        super(InvitationTestCaseRegistration, self).setUp()
        self.saved_invitation_use_allauth = settings.INVITATION_USE_ALLAUTH
        settings.INVITATION_USE_ALLAUTH = False
        self.saved_socialaccount_providers = settings.SOCIALACCOUNT_PROVIDERS
        settings.SOCIALACCOUNT_PROVIDERS = {}   
        
    def tearDown(self):
        super(InvitationTestCaseRegistration, self).tearDown()
        settings.INVITATION_USE_ALLAUTH = self.saved_invitation_use_allauth 
        settings.SOCIALACCOUNT_PROVIDERS = self.saved_socialaccount_providers 
        
class InvitationTestCaseAllauth(InvitationTestCase):
    
    def setUp(self):
        super(InvitationTestCaseAllauth, self).setUp()
        self.saved_invitation_use_allauth = settings.INVITATION_USE_ALLAUTH
        settings.INVITATION_USE_ALLAUTH = True
        self.saved_socialaccount_providers = settings.SOCIALACCOUNT_PROVIDERS
        settings.SOCIALACCOUNT_PROVIDERS = {}   

        self.facebook_app = SocialApp(provider='facebook', name='test', key='abc', secret='def')
        self.facebook_app.save()
        
        
    def tearDown(self):
        super(InvitationTestCaseAllauth, self).tearDown()
        settings.INVITATION_USE_ALLAUTH = self.saved_invitation_use_allauth 
        settings.SOCIALACCOUNT_PROVIDERS = self.saved_socialaccount_providers             
            

class InvitationModelTests(InvitationTestCase):
    """
    Tests for the model-oriented functionality of django-invitation.
    
    """
    def test_invitation_key_created(self):
        """
        Test that a ``InvitationKey`` is created for a new key.
        
        """
        self.assertEqual(InvitationKey.objects.count(), 2)

    def test_invitation_email(self):
        """
        Test that ``InvitationKey.send_to`` sends an invitation email.
        
        """
        self.sample_key.send_to('bob@example.com')
        self.assertEqual(len(mail.outbox), 1)

    def test_key_expiration_condition(self):
        """
        Test that ``InvitationKey.key_expired()`` returns ``True`` for expired 
        keys, and ``False`` otherwise.
        
        """
        # Unexpired user returns False.
        self.failIf(self.sample_key.key_expired())

        # Expired user returns True.
        self.failUnless(self.expired_key.key_expired())

    def test_expired_user_deletion(self):
        """
        Test ``InvitationKey.objects.delete_expired_keys()``.
        
        Only keys whose expiration date has passed are deleted by 
        delete_expired_keys.
        
        """
        InvitationKey.objects.delete_expired_keys()
        self.assertEqual(InvitationKey.objects.count(), 1)

    def test_management_command(self):
        """
        Test that ``manage.py cleanupinvitation`` functions correctly.
        
        """
        management.call_command('cleanupinvitation')
        self.assertEqual(InvitationKey.objects.count(), 1)
        
    def test_invitations_remaining(self):
        """Test InvitationUser calculates remaining invitations properly."""
        remaining_invites = InvitationKey.objects.remaining_invitations_for_user

        # New user starts with settings.INVITATIONS_PER_USER
        user = User.objects.create_user(username='newbie',
                                        password='secret',
                                        email='newbie@example.com')
        self.assertEqual(remaining_invites(user), settings.INVITATIONS_PER_USER)

        # After using some, amount remaining is decreased
        used = InvitationKey.objects.filter(from_user=self.sample_user).count()
        expected_remaining = settings.INVITATIONS_PER_USER - used
        remaining = remaining_invites(self.sample_user)
        self.assertEqual(remaining, expected_remaining)
        
        # Using Invitationuser via Admin, remaining can be increased
        invitation_user = InvitationUser.objects.get(inviter=self.sample_user)
        new_remaining = 2*settings.INVITATIONS_PER_USER + 1
        invitation_user.invitations_remaining = new_remaining
        invitation_user.save()
        remaining = remaining_invites(self.sample_user)
        self.assertEqual(remaining, new_remaining)

        # If no InvitationUser (for pre-existing/legacy User), one is created
        old_sample_user = User.objects.create_user(username='lewis',
                                                   password='secret',
                                                   email='lewis@example.com')
        old_sample_user.invitationuser_set.all().delete()
        self.assertEqual(old_sample_user.invitationuser_set.count(), 0)
        remaining = remaining_invites(old_sample_user)
        self.assertEqual(remaining, settings.INVITATIONS_PER_USER)

        
class InvitationFormTests(InvitationTestCase):
    """
    Tests for the forms and custom validation logic included in
    django-invitation.
    
    """
    def setUp(self):
        super(InvitationFormTests, self).setUp()
        self.saved_invitation_blacklist = settings.INVITATION_BLACKLIST
        settings.INVITATION_BLACKLIST = ( '@mydomain.com', )
 
    def tearDown(self):
        settings.INVITATION_BLACKLIST = self.saved_invitation_blacklist
        super(InvitationFormTests, self).tearDown()
       
    def test_invalid_invitation_form(self):
        """
        Test that ``InvitationKeyForm`` enforces email constraints.
        
        """
        invalid_data_dicts = [
            # Invalid email.
            {
            'data': { 'email': 'example.com' },
            'error': ('email', [u"Enter a valid e-mail address."])
            },
            {
             'data': {'email': 'an_address@mydomain.com'},
             'error': ('email', [u"Thanks, but there's no need to invite us!"])
            }                  
            ]

        for invalid_dict in invalid_data_dicts:
            form = forms.InvitationKeyForm(data=invalid_dict['data'], remaining_invitations=1)
            self.failIf(form.is_valid())
            self.assertEqual(form.errors[invalid_dict['error'][0]], invalid_dict['error'][1])

    def test_invitation_form(self):
        form = forms.InvitationKeyForm(data={ 'email': 'foo@example.com' ,}, remaining_invitations=1 )
        print(form.errors)
        self.failUnless(form.is_valid())


class InvitationViewTestsRegistration(InvitationTestCaseRegistration):
    """
    Tests for the views included in django-invitation when django-registration is used as the backend.
    
    """
    
    def test_invitation_view(self):
        """
        Test that the invitation view rejects invalid submissions,
        and creates a new key and redirects after a valid submission.
        
        """
        # You need to be logged in to send an invite.
        response = self.client.login(username='alice', password='secret')
        remaining_invitations = InvitationKey.objects.remaining_invitations_for_user(self.sample_user)
        
        # Invalid email data fails.
        response = self.client.post(reverse('invitation_invite'),
                                    data={ 'email': 'example.com' })
        self.assertEqual(response.status_code, 200)
        self.failUnless(response.context['form'])
        self.failUnless(response.context['form'].errors)

        # Valid email data succeeds.
        response = self.client.post(reverse('invitation_invite'),
                                    data={ 'email': 'foo@example.com' })
        self.assertRedirect(response, 'invitation_complete')
        self.assertEqual(InvitationKey.objects.count(), 3)
        self.assertEqual(InvitationKey.objects.remaining_invitations_for_user(self.sample_user), remaining_invitations-1)
        
        # Once remaining invitations exhausted, you fail again.
        while InvitationKey.objects.remaining_invitations_for_user(self.sample_user) > 0:
            self.client.post(reverse('invitation_invite'),
                             data={'email': 'foo@example.com'})
        self.assertEqual(InvitationKey.objects.remaining_invitations_for_user(self.sample_user), 0)
        response = self.client.post(reverse('invitation_invite'),
                                    data={'email': 'foo@example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['remaining_invitations'], 0)
        self.failUnless(response.context['form'])
    
    def test_invited_view(self):
        """
        Test that the invited view invite the user from a valid
        key and fails if the key is invalid or has expired.
       
        """
        # Valid key puts use the invited template.
        response = self.client.get(reverse('invitation_invited',
                                           kwargs={ 'invitation_key': self.sample_key.key }))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'invitation/invited.html')

        # Expired key use the wrong key template.
        response = self.client.get(reverse('invitation_invited',
                                           kwargs={ 'invitation_key': self.expired_key.key }))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'invitation/wrong_invitation_key.html')

        # Invalid key use the wrong key template.
        response = self.client.get(reverse('invitation_invited',
                                           kwargs={ 'invitation_key': 'foo' }))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'invitation/wrong_invitation_key.html')

        # Nonexistent key use the wrong key template.
        hash = hashlib.md5()
        hash.update('foo'.encode("utf-8"))
        response = self.client.get(reverse('invitation_invited',
                                           kwargs={ 'invitation_key': hash.hexdigest() }))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'invitation/wrong_invitation_key.html')

    def test_register_view(self):
        """
        Test that after registration a key cannot be reused.
        
        """        
        # This won't work if registration isn't installed
        if not registration_installed:
            print("** Skipping test requiring django-registration **")
            return 
        
        # The first use of the key to register a new user works.
        registration_data = self.sample_registration_data.copy()
        response = self.client.post(reverse('registration_register'), 
                                    data=registration_data)
        self.assertRedirect(response, 'registration_complete')
        user = User.objects.get(username='new_user')
        key = InvitationKey.objects.get_key(self.sample_key.key)
        self.assertEqual(user, key.registrant)

        # Trying to reuse the same key then fails.
        registration_data['username'] = 'even_newer_user'
        response = self.client.post(reverse('registration_register'), 
                                    data=registration_data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 
                                'invitation/wrong_invitation_key.html')
        try:        
            even_newer_user = User.objects.get(username='even_newer_user')
            self.fail("Invitation already used - No user should be created.")
        except User.DoesNotExist:
            pass
 
class InvitationViewTestsAllauth(InvitationTestCaseAllauth):
    """
    Tests for the views included in django-invitation when django-allauth is used as the backend.
    
    """
    
    def test_invitation_view(self):
        """
        Test that the invitation view rejects invalid submissions,
        and creates a new key and redirects after a valid submission.
        
        """
        # You need to be logged in to send an invite.
        response = self.client.login(username='alice', password='secret')
        remaining_invitations = InvitationKey.objects.remaining_invitations_for_user(self.sample_user)
        
        # Invalid email data fails.
        response = self.client.post(reverse('invitation_invite'),
                                    data={ 'email': 'example.com' })
        self.assertEqual(response.status_code, 200)
        self.failUnless(response.context['form'])
        self.failUnless(response.context['form'].errors)

        # Valid email data succeeds.
        response = self.client.post(reverse('invitation_invite'),
                                    data={ 'email': 'foo@example.com' })
        self.assertRedirect(response, 'invitation_complete')
        self.assertEqual(InvitationKey.objects.count(), 3)
        self.assertEqual(InvitationKey.objects.remaining_invitations_for_user(self.sample_user), remaining_invitations-1)
        
        # Once remaining invitations exhausted, you fail again.
        while InvitationKey.objects.remaining_invitations_for_user(self.sample_user) > 0:
            self.client.post(reverse('invitation_invite'),
                             data={'email': 'foo@example.com'})
        self.assertEqual(InvitationKey.objects.remaining_invitations_for_user(self.sample_user), 0)
        response = self.client.post(reverse('invitation_invite'),
                                    data={'email': 'foo@example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['remaining_invitations'], 0)
        self.failUnless(response.context['form'])
    
    def test_invited_view(self):
        """
        Test that the invited view invite the user from a valid
        key and fails if the key is invalid or has expired.
       
        """
        # Valid key puts use the invited template.
        response = self.client.get(reverse('invitation_invited',
                                           kwargs={ 'invitation_key': self.sample_key.key }))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'invitation/invited.html')

        # Expired key use the wrong key template.
        response = self.client.get(reverse('invitation_invited',
                                           kwargs={ 'invitation_key': self.expired_key.key }))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'invitation/wrong_invitation_key.html')

        # Invalid key use the wrong key template.
        response = self.client.get(reverse('invitation_invited',
                                           kwargs={ 'invitation_key': 'foo' }))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'invitation/wrong_invitation_key.html')

        # Nonexistent key use the wrong key template.
        hash = hashlib.md5()
        hash.update('foo'.encode('utf-8'))
        response = self.client.get(reverse('invitation_invited',
                                           kwargs={ 'invitation_key': hash.hexdigest() }))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'invitation/wrong_invitation_key.html')

    def test_register_view(self):
        """
        Test that after registration a key cannot be reused.
        
        """        
        # This won't work if registration isn't installed
        if not allauth_installed:
            print("** Skipping test requiring django-allauth **")
            return 
        
        # The first use of the key to register a new user works.
        registration_data = self.sample_allauth_data.copy()
        
        # User has to go through 'invited' first
        response = self.client.get(reverse('invitation_invited', kwargs={'invitation_key' : self.sample_key.key }))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 
                                'invitation/invited.html')
        
        # If the key gets approved it should be stored in the session
        self.assertIn('invitation_key', self.client.session)
                
        response = self.client.post(reverse('account_signup'), data=registration_data)
        self.assertEqual(response.status_code, 302)
        
        # Check that the key has been removed from the session data
        self.assertNotIn('invitation_key', self.client.session)
        
        # self.assertRedirect(response, 'registration_complete')
        user = User.objects.get(username='new_user')
        key = InvitationKey.objects.get_key(self.sample_key.key)
        self.assertIn(key, user.invitations_used.all())

        # Trying to reuse the same key then fails.
        registration_data['username'] = 'even_newer_user'
        response = self.client.post(reverse('invitation_invited', kwargs={'invitation_key' : self.sample_key.key }))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 
                                'invitation/wrong_invitation_key.html')

        
class InviteModeOffTestsRegistration(InvitationTestCaseRegistration):
    """
    Tests for the case where INVITE_MODE is False and django-registration is used as the backend.
    
    (The test cases other than this one generally assume that INVITE_MODE is 
    True.)
    
    """
    def setUp(self):
        super(InviteModeOffTestsRegistration, self).setUp()
        self.saved_invite_mode = settings.INVITE_MODE
        settings.INVITE_MODE = False
        self.saved_socialaccount_providers = settings.SOCIALACCOUNT_PROVIDERS
        settings.SOCIALACCOUNT_PROVIDERS = {}        
 
    def tearDown(self):
        settings.INVITE_MODE = self.saved_invite_mode
        settings.SOCIALACCOUNT_PROVIDERS = self.saved_socialaccount_providers
        super(InviteModeOffTestsRegistration, self).tearDown()
       
    def test_invited_view(self):
        """
        Test that the invited view redirects to registration_register.
       
        """
        # This won't work if registration isn't installed
        if not registration_installed:
            print("** Skipping test requiring django-registration **")
            return 
        
        response = self.client.get(reverse('invitation_invited',
                            kwargs={ 'invitation_key': self.sample_key.key }))
        self.assertRedirect(response, 'registration_register')

    def test_register_view(self):
        """
        Test register view.  
        
        With INVITE_MODE = FALSE, django-invitation just passes this view on to
        django-registration's register.
       
        """
        # This won't work if registration isn't installed
        if not registration_installed:
            return 
        
        # get
        response = self.client.get(reverse('registration_register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'registration/registration_form.html')
        
        # post
        response = self.client.post(reverse('registration_register'), 
                                    data=self.sample_registration_data)
        self.assertRedirect(response, 'registration_complete')
        
class InviteModeOffTestsAllauth(InvitationTestCaseAllauth):
    """
    Tests for the case where INVITE_MODE is False and django-allauth is used as the backend.
    
    (The test cases other than this one generally assume that INVITE_MODE is 
    True.)
    
    """
    def setUp(self):
        super(InviteModeOffTestsAllauth, self).setUp()
        self.saved_invite_mode = settings.INVITE_MODE
        settings.INVITE_MODE = False
        self.saved_socialaccount_providers = settings.SOCIALACCOUNT_PROVIDERS
        settings.SOCIALACCOUNT_PROVIDERS = {}        
 
    def tearDown(self):
        settings.INVITE_MODE = self.saved_invite_mode
        settings.SOCIALACCOUNT_PROVIDERS = self.saved_socialaccount_providers
        super(InviteModeOffTestsAllauth, self).tearDown()
       
    def test_invited_view(self):
        """
        Test that the invited view redirects to registration_register.
       
        """
        # This won't work if registration isn't installed
        if not allauth_installed:
            print("** Skipping test requiring django-allauth **")
            return 
        
        response = self.client.get(reverse('invitation_invited',
                            kwargs={ 'invitation_key': self.sample_key.key }))
        self.assertRedirect(response, 'registration_register')

    def test_register_view(self):
        """
        Test register view.  
        
        With INVITE_MODE = FALSE, django-invitation just passes this view on to
        django-registration's register.
       
        """
        # This won't work if registration isn't installed
        if not allauth_installed:
            print("** Skipping test requiring django-allauth **")
            return 
        
        # TODO fix this.  But for now I'm not going to bother since we could simply remove 
        # invitation altogether if we don't want to use the invitation code, or bypass the URL somehow.  
        response = self.client.get(reverse('registration_register'))
        self.assertEqual(response.status_code, 302)
        self.assertTemplateUsed(response, 'account/signup.html')
