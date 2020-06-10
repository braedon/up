% rebase('base.tpl', title='up? - Link Down')
<div id="content">
  <h1>down!</h1>
  <div class="message">
    That <a href="{{url}}" target="_blank" rel="noopener noreferrer">link</a> does seem to be down.
  </div>
  <div class="message">
    Submit an email address to get notified when it's up again.
  </div>
  <form action="/submit" method="POST">
    <input type="hidden" name="url" value="{{url}}" />
    <input type="email" name="email" autocomplete="email" placeholder="email" required/>
    <button>Submit</button>
  </form>
  <div class="message">
    <a href="/">Got another link?</a>
  </div>
</div>
