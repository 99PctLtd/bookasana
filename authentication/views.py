import sendgrid

from decouple import config
from django.contrib import messages
from django.contrib.auth import (
    authenticate, login, logout,
    update_session_auth_hash
)
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.views import PasswordResetView
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
# from django.forms.utils import ErrorList
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils.encoding import force_bytes, force_text
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from django.views.generic import View

from .tokens import account_activation_token
from .forms import (
    CustomUserActivationForm,
    CustomUserCreationForm,
    EditProfileForm,
    MyPasswordResetForm
)
from .models import User
from .task_confirmation_check import account_validation, parse_validated_account
from .email_utils import send_grid_email


def account_activation_sent(request):
    return render(request, 'authentication/account_activation_sent.html')


class ChangePassword(View):
    form_class = PasswordChangeForm
    success_url = 'account:my_info'
    template = 'authentication/change_password.html'

    # display blank form
    def get(self, request):
        form = self.form_class(user=request.user)
        return render(request, self.template, {'form': form})

    # process form data
    def post(self, request):
        form = self.form_class(data=request.POST, user=request.user)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            messages.success(request, 'Your password was successfully updated!')
            return redirect(self.success_url)
        else:
            messages.error(request, 'Please correct the error below.')
            return render(request, self.template, {'form': form})


class EditProfile(View):
    form_class = EditProfileForm
    success_url = 'account:my_info'
    template = 'authentication/edit_profile.html'

    # display form with pre-filled user info
    def get(self, request):
        form = self.form_class(instance=request.user)
        return render(request, self.template, {'form': form})

    # process form data
    def post(self, request):
        pw = request.user.pure_password
        user = request.user
        form = self.form_class(data=request.POST, instance=request.user)
        if form.is_valid():
            if form.cleaned_data['pure_password']:
                if account_validation(user, form.cleaned_data['pure_login'], form.cleaned_data['pure_password']):
                    form.save()
                    messages.success(request, 'Your profile was successfully updated!')
                    return redirect(self.success_url)
                else:
                    messages.error(request, 'invalid pure login/password, please try again.')
            else:
                if account_validation(user, form.cleaned_data['pure_login'], pw):
                    edit_form = form.save(commit=False)
                    edit_form.first_name = form.cleaned_data['first_name']
                    edit_form.last_name = form.cleaned_data['last_name']
                    edit_form.mobile_phone = form.cleaned_data['mobile_phone']
                    edit_form.email = form.cleaned_data['pure_login']
                    edit_form.pure_login = form.cleaned_data['pure_login']
                    edit_form.pure_password = pw
                    edit_form.save()
                    user.email = form.cleaned_data['pure_login']
                    user.save()
                    messages.success(request, 'Your profile was successfully updated!')
                    return redirect(self.success_url)
                else:
                    messages.error(request, 'invalid pure login, please try again.')
            return render(request, self.template, {'form': form})
        else:
            messages.error(request, 'Please correct the error below.')
            return render(request, self.template, {'form': form})


class MyPasswordResetView(PasswordResetView):
    form_class = MyPasswordResetForm


class UserLogin(View):
    form_class = AuthenticationForm
    template = 'authentication/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            messages.error(request, 'You are already logged in.')
            return redirect('schedule:schedule_current')
        else:
            form = self.form_class(None)
            return render(request, self.template, {'form': form})

    def post(self, request):
        form = self.form_class(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user is not None:
                if user.is_active:
                    login(request, user)
                    return redirect('schedule:schedule_current')
        return render(request, self.template, {'form': form})


class UserLogout(View):

    def post(self, request):
        logout(request)
        return redirect('index')


class UserActivate(View):
    form_class = CustomUserActivationForm
    success_url = 'schedule:schedule_current'
    template = 'authentication/account_activation_confirm.html'

    # display form with pre-filled user info
    # there should only be pure login
    def get(self, request, uidb64, token):
        try:
            uid = force_text(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and account_activation_token.check_token(user, token):
            login(request, user)
            form = self.form_class(instance=request.user)
            return render(request, self.template, {
                'form': form,
                'username': user.username,
            })
        else:
            return render(request, 'authentication/account_activation_invalid.html')

    # process form data
    def post(self, request, uidb64, token):
        try:
            uid = force_text(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and account_activation_token.check_token(user, token):
            login(request, user)
            form = self.form_class(data=request.POST, instance=request.user)
            if form.is_valid():
                if account_validation(user, form.cleaned_data['pure_login'], form.cleaned_data['pure_password']):
                    user.is_active = True
                    user.email_confirmed = True

                    first_name = form.cleaned_data['first_name']
                    last_name = form.cleaned_data['last_name']
                    mobile_phone = form.cleaned_data['mobile_phone']
                    email = form.cleaned_data['pure_login']
                    pure_login = form.cleaned_data['pure_login']
                    pure_password = form.cleaned_data['pure_password']
                    email = form.cleaned_data['pure_login']

                    user.save()
                    login(request, user)

                    parse_validated_account.delay(uid)
                    return redirect(self.success_url)
                else:
                    messages.error(request, 'invalid pure login/password, please try again.')
                    return render(request, self.template, {
                        'form': form,
                        'username': user.username,
                    })
            else:
                messages.error(request, 'please correct the error below.')
                return render(request, self.template, {
                    'form': form,
                    'username': user.username,
                })
        else:
            return render(request, 'authentication/account_activation_invalid.html')


class UserSignUp(View):
    form_class = CustomUserCreationForm
    close_list = 'authentication/registration_close.html'
    template = 'authentication/signup.html'

    # display blank form
    def get(self, request):
        if request.user.is_authenticated:
            messages.warning(request, 'Please logout for new registration.')
            return redirect('schedule:schedule_current')
        else:
            if User.objects.count() < 50:
                form = self.form_class(None)
                return render(request, self.template, {'form': form})
            else:
                return render(request, self.close_list)

    # process form data
    def post(self, request):
        form = self.form_class(request.POST)

        if form.is_valid():
            if form.cleaned_data['agree_to_terms_privacy']:
                user = form.save(commit=False)
                user.agree_to_terms_privacy = True
                user.is_active = False
                user.save()

                current_site = get_current_site(request)

                # Digital Ocean disable sending mail in the first 60 days...
                # ==================================================
                # subject = 'Activate your Bookasana account'
                # message = render_to_string('authentication/email_account_activation.html', {
                #     'user': user,
                #     'domain': current_site.domain,
                #     'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                #     'token': account_activation_token.make_token(user),
                # })
                # user.email_user(subject, message)
                # send_mail(subject, message, 'admin@bookasana.com', [user.pure_login], fail_silently=False)

                send_grid_email(
                    {
                        'user': user,
                        'protocol': request.scheme,
                        'domain': current_site.domain,
                        'uid_token': reverse_lazy(
                            'authentication:activate',
                            kwargs={
                                'uidb64': urlsafe_base64_encode(force_bytes(user.pk)),
                                'token': account_activation_token.make_token(user),
                            }
                        ),
                    },
                    activation=True,
                )
                return redirect('authentication:account_activation_sent')
            else:
                return render(request, self.template, {'form': form})
        return render(request, self.template, {'form': form})
