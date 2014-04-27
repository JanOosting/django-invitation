django-invitation
=================
Forked from https://github.com/lizrice/django-invitation which is forked from http://code.larlet.fr/django-invitation.

### This version has been modified to offer the option of using django-allauth as the authentication backend:
- Does not require any modifications to django-allauth. 
- Utilizes is_open_for_signup method to integrate the invitation system with allauth. 
- Uses the recipient email to bypass email verification in allauth cince we have verified it.
- Stores the invitation recipient in the model to allow tracking & email verification.

V1.1
----
***recipiant added to model (email field):***  
-This allows us to track recipients. For example we may want to email all recipients a few days prior to expiration.  
-It also allows us to pre-populate form data with the recipient email address and validate it.  
-Compatable with null values.  
***session is now passed the invitation_key object instead of just the key value:***  
***create_bulk_invitation:***  
-Default recipient = None  
***send_bulk_invitations:***  
-Includes a recipient for each invitation sent.  
***Backwards compatable:***  
-Including the recipient email address in the invitation url is optional so the upgrade is backwards compatible with 
previously sent invitations using this format.  This will be removed at a later date.  
***includes south migrations:***  

Django Allauth integration
--------------------------
***1)*** Follow the setup instructions for django-invitation: 
http://code.larlet.fr/django-invitation/wiki/Home 

***2)*** Create an accountadapter.py file and locate it in your project diretory.

NOTE: if you are using the account adapter exactly as writen below, make sure you specify DEFAULT_USER_GROUP in your settings.

Example accountadapter.py: 

    from allauth.account.adapter import DefaultAccountAdapter
	from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
	from allauth.exceptions import ImmediateHttpResponse
	from invitation.models import InvitationKey
	from allauth.account.signals import user_signed_up

	from django.conf import settings
	from django.contrib.auth.models import Group
	from django.dispatch import receiver
	from django.shortcuts import render

	
	class AccountAdapter(DefaultAccountAdapter):
		"""
		Checks whether or not the site is open for signups.
		Next to simply returning True/False you can also intervene the
		regular flow by raising an ImmediateHttpResponse
		"""
		def is_open_for_signup(self, request):
			#print 'is open for sign up session keys', request.session.keys()
			if getattr(settings, 'ALLOW_NEW_REGISTRATIONS', False):
				if getattr(settings, 'INVITE_MODE', False):
					invitation_key = request.session.get('invitation_key', False)
					if invitation_key:
						if InvitationKey.objects.is_key_valid(invitation_key.key):
							invitation_recipient = request.session.get('invitation_recipient', False)
							self.stash_verified_email(request, invitation_recipient[0])
							return True
						else:
							extra_context = request.session.get('invitation_context', {})
							template_name = 'invitation/wrong_invitation_key.html'
							raise ImmediateHttpResponse(render(request,template_name, extra_context))
				else:
					return True
			return False

		@receiver (user_signed_up)
		def complete_signup(sender, **kwargs):
			user = kwargs.pop('user')
			request = kwargs.pop('request')
			#sociallogin = request.session.get('socialaccount_sociallogin', None)

			# Handle user permissions
			user.groups.add(Group.objects.get(name=settings.DEFAULT_USER_GROUP))
			user.save()

			# Handle invitation if required
			if 'invitation_key' in request.session.keys():
				invitation_key = request.session.get('invitation_key', False)
				invitation_key.mark_used(user)
				del request.session['invitation_key']
				del request.session['invitation_recipient']
				del request.session['invitation_context']


***3)*** In your settings point ACCOUNT_ADAPTER to the accountadapter.py file you created above (this is required):  
ACCOUNT_ADAPTER ="myprojectname.accountadapter.AccountAdapter"

***4)*** Add the setting `INVITATION_USE_ALLAUTH = True` and `'INVITE_MODE' = True` to your settings.

***5)*** add ALLOW_NEW_REGISTRATIONS = True/False to your settings file:
This setting allows you to block all new registrations even with a valid invitation.


