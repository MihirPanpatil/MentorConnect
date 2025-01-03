from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from channels.layers import get_channel_layer
from django.contrib import messages
from asgiref.sync import async_to_sync
from django.http import HttpResponse
from django.http import Http404
from .models import *
from .forms import *

# Create your views here.
@login_required
def chat_view(request, chatroom_name='public-chat'):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    chat_messages = chat_group.chat_messages.all()[:30]
    form = ChatmessageCreateForm()

    other_user = None

    if chat_group.is_private:
        if request.user not in chat_group.members.all():
            raise Http404()
        for member in chat_group.members.all():
            if member != request.user:
                other_user = member
                break

    private_chats = request.user.chat_groups.filter(is_private=True)
    group_chats = request.user.chat_groups.filter(is_private=False)

    if chat_group.groupchat_name:
        if request.user not in chat_group.members.all():
            if request.user.emailaddress_set.filter(verified=True).exists():
                chat_group.members.add(request.user)
            else:
                messages.warning(request, 'You need to verify your email to join the chat!')
                return redirect('profile-settings')


    if request.htmx:
        form = ChatmessageCreateForm(request.POST)
        if form.is_valid:
            message = form.save(commit=False)
            message.author = request.user
            message.group = chat_group
            message.save()
            context = {
                'message' : message,
                'user' : request.user
            }
            return render(request, 'a_rtchat/partials/chat_message_p.html', context)
        
    context = {
        'chat_messages': chat_messages,
        'form': form,
        'other_user': other_user,
        'chatroom_name': chatroom_name,
        'chat_group': chat_group,
        'private_chats': private_chats,
        'group_chats': group_chats
    }
 
    return render(request, 'a_rtchat/chat.html', context)

@login_required
def get_or_create_chatroom(request, username):
    if request.user.username == username:
        return redirect('home')

    other_user = User.objects.get(username = username)
    my_chatrooms = request.user.chat_groups.filter(is_private=True)

    if my_chatrooms.exists():
        for chatroom in my_chatrooms:
            if other_user in chatroom.members.all():
                chatroom = chatroom
                break
            else:
                chatroom = ChatGroup.objects.create(is_private = True)
                chatroom.members.add(other_user, request.user)
    else:
        chatroom = ChatGroup.objects.create(is_private = True)
        chatroom.members.add(other_user, request.user)
        
    return redirect('chatroom', chatroom.group_name)

@login_required
def create_groupchat(request):
    if request.method == 'POST':
        form = NewGroupForm(request.POST)
        if form.is_valid():
            chat_group = form.save(commit=False)
            chat_group.admin = request.user
            chat_group.save()
            chat_group.members.add(request.user)
            messages.success(request, 'Chat group created successfully')
            return redirect('chatroom', chat_group.group_name)
    else:
        form = NewGroupForm()
    return render(request, 'a_rtchat/create_groupchat.html', {'form': form})


@login_required
def chatroom_edit_view(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user != chat_group.admin:
        raise Http404()
    
    form = ChatRoomEditForm(instance=chat_group) 

    if request.method == 'POST':
        form = ChatRoomEditForm(request.POST, instance=chat_group)
        if form.is_valid():
            form.save()
            
            remove_members = request.POST.getlist('remove_members')
            for member_id in remove_members:
                member = User.objects.get(id=member_id)
                chat_group.members.remove(member)  
                
            return redirect('chatroom', chatroom_name) 

    context = {
        'form' : form,
        'chat_group' : chat_group
    }   
    return render(request, 'a_rtchat/chatroom_edit.html', context) 



@login_required
def chatroom_delete_view(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user != chat_group.admin:
        raise Http404()
    
    if request.method == "POST":
        chat_group.delete()
        messages.success(request, 'Chatroom deleted')
        return redirect('home')
    
    return render(request, 'a_rtchat/chatroom_delete.html', {'chat_group':chat_group})


def chat_file_upload(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    
    if request.htmx and request.FILES:
        file = request.FILES['file']
        message = GroupMessage.objects.create(
            file = file,
            author = request.user, 
            group = chat_group,
        )
        channel_layer = get_channel_layer()
        event = {
            'type': 'message_handler',
            'message_id': message.id,
        }
        async_to_sync(channel_layer.group_send)(
            chatroom_name, event
        )
    return HttpResponse()

@login_required
def manage_chat_members(request, chatroom_name):
    chat_group = get_object_or_404(ChatGroup, group_name=chatroom_name)
    if request.user != chat_group.admin:
        raise Http404()
        
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')
        
        if user_id and action:
            user = get_object_or_404(User, id=user_id)
            if action == 'add':
                chat_group.members.add(user)
            elif action == 'remove':
                chat_group.members.remove(user)
                
    return redirect('chatroom', chatroom_name)